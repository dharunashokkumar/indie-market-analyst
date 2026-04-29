from __future__ import annotations

from datetime import UTC, datetime

from intraday_engine.data_sources.base import QuoteSnapshot, SurveillanceEntry
from intraday_engine.filters.apply import apply_filters
from intraday_engine.filters.asm_gsm import fetch_snapshot, load_cached_snapshot
from intraday_engine.filters.liquidity import MIN_DAILY_TURNOVER_RUPEES, check_liquidity


class _SurveillanceSource:
    name = "nse_direct"

    def __init__(self) -> None:
        self.calls = 0

    def fetch_asm_gsm(self):
        self.calls += 1
        return [
            SurveillanceEntry(
                symbol="RELIANCE",
                list_type="ASM",
                stage="Stage I",
                as_of=datetime.now(UTC),
            )
        ]


def _quote(symbol: str, turnover: float) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        ltp=100.0,
        volume=turnover / 100.0,
        turnover=turnover,
        as_of=datetime.now(UTC),
        source="nse_direct",
    )


def test_asm_gsm_snapshot_uses_daily_cache(tmp_path, monkeypatch):
    from intraday_engine.filters import asm_gsm

    monkeypatch.setattr(asm_gsm, "FILTERS_DIR", tmp_path)
    source = _SurveillanceSource()

    first = fetch_snapshot(source=source, market_date="2026-04-29")
    second = fetch_snapshot(source=source, market_date="2026-04-29")
    cached = load_cached_snapshot("2026-04-29")

    assert source.calls == 1
    assert first.entries[0].symbol == "RELIANCE"
    assert second.entries[0].list_type == "ASM"
    assert cached is not None
    assert cached.market_date == "2026-04-29"


def test_liquidity_checks_turnover_floor():
    low = check_liquidity("LOW", quote=_quote("LOW", MIN_DAILY_TURNOVER_RUPEES - 1))
    high = check_liquidity("HIGH", quote=_quote("HIGH", MIN_DAILY_TURNOVER_RUPEES))

    assert low.passed is False
    assert low.reason == "below_turnover_floor"
    assert high.passed is True


def test_apply_filters_tags_surveillance_and_rejects_low_liquidity():
    entries = [
        SurveillanceEntry(
            symbol="RELIANCE",
            list_type="GSM",
            stage=None,
            as_of=datetime.now(UTC),
        )
    ]
    result = apply_filters(
        ["RELIANCE", "LOWTURN"],
        quotes={
            "RELIANCE": _quote("RELIANCE", MIN_DAILY_TURNOVER_RUPEES * 2),
            "LOWTURN": _quote("LOWTURN", 1_000_000.0),
        },
        asm_gsm_entries=entries,
    )

    assert result.input_count == 2
    assert result.output_count == 1
    assert result.symbols[0].symbol == "RELIANCE"
    assert result.symbols[0].asm_gsm_tags == ["GSM"]
    assert result.rejected[0].symbol == "LOWTURN"
    assert result.rejected[0].stage == "liquidity"
