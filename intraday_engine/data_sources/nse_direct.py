"""Cookie-backed NSE India data source."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from intraday_engine.data_sources.base import (
    Candle,
    DataSource,
    DataSourceError,
    PreOpenRow,
    QuoteSnapshot,
    SurveillanceEntry,
)
from intraday_engine.data_sources.settings_store import IntradaySettings, load_settings

BASE_URL = "https://www.nseindia.com"
ARCHIVE_BASE_URL = "https://archives.nseindia.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

ASM_GSM_CSVS = (
    (
        "ASM",
        "/content/equities/Additional Surveillance Measure (ASM) - List of Securities.csv",
    ),
    (
        "GSM",
        "/content/equities/Graded Surveillance Measure (GSM) - List of Securities.csv",
    ),
)


class NseDirectSource(DataSource):
    name = "nse_direct"

    def __init__(self, settings: IntradaySettings | None = None) -> None:
        self.settings = settings or load_settings()

    def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "5m",
        lookback: str = "1d",
    ) -> list[Candle]:
        if _lookback_days(lookback) > 1:
            raise DataSourceError("NSE direct chart endpoint only supports current-day candles")
        symbol = symbol.strip().upper()
        identifiers = self._chart_identifiers(symbol)
        last_error: Exception | None = None
        for identifier in identifiers:
            try:
                payload = self._get_json(
                    "/api/chart-databyindex",
                    params={"index": identifier, "indices": "false"},
                )
                candles = _chart_payload_to_candles(payload, interval)
                if candles:
                    return candles
            except Exception as exc:
                last_error = exc
        detail = f": {last_error}" if last_error else ""
        raise DataSourceError(f"NSE direct returned no candles for {symbol}{detail}")

    def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        symbol = symbol.strip().upper()
        payload = self._get_json("/api/quote-equity", params={"symbol": symbol})
        price = payload.get("priceInfo") if isinstance(payload.get("priceInfo"), dict) else {}
        sec = (
            payload.get("securityWiseDP")
            if isinstance(payload.get("securityWiseDP"), dict)
            else {}
        )
        ltp = _float(price.get("lastPrice"))
        if ltp is None:
            raise DataSourceError(f"NSE direct returned no last price for {symbol}")
        prev_close = _float(price.get("previousClose") or price.get("prevClose"))
        pct_change = _float(price.get("pChange"))
        return QuoteSnapshot(
            symbol=symbol,
            ltp=ltp,
            prev_close=prev_close,
            pct_change=pct_change / 100 if pct_change is not None else None,
            day_high=_float(price.get("intraDayHighLow", {}).get("max") if isinstance(
                price.get("intraDayHighLow"), dict
            ) else price.get("dayHigh")),
            day_low=_float(price.get("intraDayHighLow", {}).get("min") if isinstance(
                price.get("intraDayHighLow"), dict
            ) else price.get("dayLow")),
            volume=_float(sec.get("quantityTraded") or price.get("totalTradedVolume")),
            turnover=_float(sec.get("totalTradedValue") or price.get("totalTradedValue")),
            as_of=datetime.now(UTC),
            source=self.name,
            raw=payload,
        )

    def fetch_preopen(self) -> list[PreOpenRow]:
        payload = self._get_json("/api/market-data-pre-open", params={"key": "ALL"})
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        out: list[PreOpenRow] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            symbol = str(meta.get("symbol") or row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            out.append(
                PreOpenRow(
                    symbol=symbol,
                    ltp=_float(meta.get("lastPrice") or row.get("lastPrice")),
                    indicative_open=_float(meta.get("iep") or row.get("iep")),
                    pct_change=_percent_to_ratio(meta.get("pChange") or meta.get("change")),
                    volume=_float(meta.get("quantity") or row.get("quantity")),
                    raw=row,
                )
            )
        return out

    def fetch_asm_gsm(self) -> list[SurveillanceEntry]:
        entries: list[SurveillanceEntry] = []
        try:
            entries.extend(self._fetch_asm_report())
        except DataSourceError:
            pass
        try:
            entries.extend(self._fetch_gsm_report())
        except DataSourceError:
            pass
        if entries:
            return entries
        for list_type, path in ASM_GSM_CSVS:
            try:
                entries.extend(self._fetch_surveillance_csv(list_type, path))
            except DataSourceError:
                continue
        return entries

    def _client(self) -> httpx.Client:
        headers = dict(HEADERS)
        if self.settings.nse_cookies:
            headers["Cookie"] = self.settings.nse_cookies
        return httpx.Client(headers=headers, timeout=20.0, follow_redirects=True)

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        with self._client() as client:
            self._warm_cookies(client)
            response = client.get(f"{BASE_URL}{path}", params=params)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise DataSourceError(f"NSE endpoint {path} returned non-object JSON")
        return data

    def _get_text(self, url: str) -> str:
        with self._client() as client:
            self._warm_cookies(client)
            response = client.get(url)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _warm_cookies(client: httpx.Client) -> None:
        try:
            client.get(BASE_URL)
        except httpx.HTTPError:
            pass

    def _chart_identifiers(self, symbol: str) -> list[str]:
        identifiers = [f"{symbol}EQN", symbol]
        try:
            quote = self._get_json("/api/quote-equity", params={"symbol": symbol})
        except Exception:
            return identifiers
        info = quote.get("info") if isinstance(quote.get("info"), dict) else {}
        identifier = str(info.get("identifier") or "").strip()
        if identifier:
            identifiers.insert(0, identifier)
        return list(dict.fromkeys(identifiers))

    def _fetch_asm_report(self) -> list[SurveillanceEntry]:
        payload = self._get_json("/api/reportASM")
        now = datetime.now(UTC)
        rows: list[SurveillanceEntry] = []
        for bucket in ("longterm", "shortterm"):
            group = payload.get(bucket)
            if not isinstance(group, dict):
                continue
            data = group.get("data")
            if not isinstance(data, list):
                continue
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                symbol = _first_text(raw, "symbol", "Symbol", "SYMBOL")
                if not symbol:
                    continue
                rows.append(
                    SurveillanceEntry(
                        symbol=symbol.upper(),
                        list_type="ASM",
                        stage=_first_text(
                            raw,
                            "survCode",
                            "asmSurvIndicator",
                            "ASM STAGE",
                        ),
                        as_of=now,
                        raw={**raw, "term": bucket},
                    )
                )
        return rows

    def _fetch_gsm_report(self) -> list[SurveillanceEntry]:
        payload = self._get_json("/api/reportGSM")
        if not isinstance(payload, list):
            raise DataSourceError("NSE reportGSM returned non-list JSON")
        now = datetime.now(UTC)
        rows: list[SurveillanceEntry] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            symbol = _first_text(raw, "symbol", "Symbol", "SYMBOL")
            if not symbol:
                continue
            rows.append(
                SurveillanceEntry(
                    symbol=symbol.upper(),
                    list_type="GSM",
                    stage=_first_text(raw, "survCode", "gsmStage", "GSM STAGE"),
                    as_of=now,
                    raw=dict(raw),
                )
            )
        return rows

    def _fetch_surveillance_csv(self, list_type: str, path: str) -> list[SurveillanceEntry]:
        url = f"{ARCHIVE_BASE_URL}{path}"
        try:
            text = self._get_text(url)
        except httpx.HTTPError as exc:
            raise DataSourceError(f"NSE {list_type} CSV fetch failed: {exc}") from exc
        reader = csv.DictReader(io.StringIO(text))
        rows: list[SurveillanceEntry] = []
        now = datetime.now(UTC)
        for raw in reader:
            symbol = _first_text(raw, "Symbol", "SYMBOL", "Security Symbol", "Company")
            if not symbol:
                continue
            rows.append(
                SurveillanceEntry(
                    symbol=symbol.upper(),
                    list_type=list_type,  # type: ignore[arg-type]
                    stage=_first_text(raw, "Stage", "STAGE", "Action", "Surveillance Action"),
                    as_of=now,
                    raw=dict(raw),
                )
            )
        return rows


def _chart_payload_to_candles(payload: dict[str, Any], interval: str) -> list[Candle]:
    raw_points = (
        payload.get("grapthData")
        or payload.get("graphData")
        or payload.get("data")
        or payload.get("values")
        or []
    )
    if not isinstance(raw_points, list):
        return []

    tick_rows: list[tuple[datetime, float, float]] = []
    for raw in raw_points:
        if isinstance(raw, dict):
            raw_time = raw.get("time") or raw.get("timestamp") or raw.get("date")
            raw_price = raw.get("value") or raw.get("close") or raw.get("ltp")
            raw_volume = raw.get("volume") or 0.0
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            raw_time = raw[0]
            raw_price = raw[1]
            raw_volume = raw[2] if len(raw) >= 3 else 0.0
        else:
            continue

        ts = _parse_timestamp(raw_time)
        price = _float(raw_price)
        if ts is None or price is None or not math.isfinite(price):
            continue
        tick_rows.append((ts, price, _float(raw_volume) or 0.0))

    if not tick_rows:
        return []

    bucket_minutes = _interval_minutes(interval)
    buckets: dict[datetime, list[tuple[datetime, float, float]]] = defaultdict(list)
    for ts, price, volume in tick_rows:
        minute = (ts.minute // bucket_minutes) * bucket_minutes
        bucket_start = ts.replace(minute=minute, second=0, microsecond=0)
        buckets[bucket_start].append((ts, price, volume))

    candles: list[Candle] = []
    for bucket_start in sorted(buckets):
        points = sorted(buckets[bucket_start], key=lambda item: item[0])
        prices = [item[1] for item in points]
        volumes = [item[2] for item in points]
        candles.append(
            Candle(
                timestamp=bucket_start,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(volume for volume in volumes if volume >= 0),
                source="nse_direct",
            )
        )
    return candles


def _interval_minutes(interval: str) -> int:
    text = interval.strip().lower()
    if text.endswith("m"):
        value = _float(text[:-1])
        if value and value >= 1:
            return int(value)
    return 5


def _lookback_days(lookback: str) -> int:
    text = lookback.strip().lower()
    if text.endswith("d"):
        value = _float(text[:-1])
        if value is not None and value > 0:
            return int(value)
    return 1


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        ts = datetime.fromtimestamp(seconds, tz=UTC)
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "NA", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _percent_to_ratio(value: Any) -> float | None:
    number = _float(value)
    return number / 100 if number is not None else None


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def market_day_lookback(days: int = 1) -> tuple[str, str]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    return start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")
