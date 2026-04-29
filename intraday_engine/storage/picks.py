"""JSON storage for intraday scan results and active picks."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from intraday_engine.ist_clock import to_ist
from intraday_engine.output_schema import ActivePick, Pick, ScanResult, utc_now
from intraday_engine.storage.paths import PICKS_DIR, ensure_intraday_dirs


def market_day(value: str | date | None = None) -> str:
    if value is None:
        return to_ist().date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def picks_day_dir(value: str | date | None = None) -> Path:
    ensure_intraday_dirs()
    path = PICKS_DIR / market_day(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def scan_path(scan_id: str, value: str | date | None = None) -> Path:
    clean_id = re.sub(r"[^A-Za-z0-9_-]+", "", scan_id.strip())
    if not clean_id:
        raise ValueError("scan_id is required")
    return picks_day_dir(value) / f"scan_{clean_id}.json"


def append_scan_result(result: ScanResult, *, day: str | date | None = None) -> ScanResult:
    path = scan_path(result.scan_id, day)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return result


def read_scan_result(scan_id: str, *, day: str | date | None = None) -> ScanResult | None:
    path = scan_path(scan_id, day)
    if not path.exists():
        return None
    try:
        return ScanResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_day_scans(*, day: str | date | None = None) -> list[ScanResult]:
    path = picks_day_dir(day)
    rows: list[ScanResult] = []
    for scan_file in sorted(path.glob("scan_*.json")):
        try:
            rows.append(ScanResult.model_validate_json(scan_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda scan: scan.created_at, reverse=True)
    return rows


def active_path(*, day: str | date | None = None) -> Path:
    return picks_day_dir(day) / "active.json"


def read_active(*, day: str | date | None = None) -> list[ActivePick]:
    path = active_path(day=day)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("active", [])
    else:
        rows = []
    out: list[ActivePick] = []
    for row in rows:
        try:
            out.append(ActivePick.model_validate(row))
        except ValueError:
            continue
    return out


def write_active(records: list[ActivePick], *, day: str | date | None = None) -> list[ActivePick]:
    path = active_path(day=day)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in records],
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
    return records


def find_pick(
    symbol: str,
    *,
    scan_id: str | None = None,
    day: str | date | None = None,
) -> Pick | None:
    clean_symbol = symbol.strip().upper()
    scans = read_day_scans(day=day)
    if scan_id:
        scans = [scan for scan in scans if scan.scan_id == scan_id]
    for scan in scans:
        for pick in [*scan.picks, *scan.watch_only]:
            if pick.symbol.upper() == clean_symbol:
                return pick
    return None


def upsert_active_pick(
    pick: Pick,
    *,
    scan_id: str | None = None,
    day: str | date | None = None,
) -> ActivePick:
    clean_symbol = pick.symbol.strip().upper()
    records = read_active(day=day)
    active_id = f"{market_day(day)}:{scan_id or 'manual'}:{clean_symbol}"
    next_record = ActivePick(
        active_id=active_id,
        scan_id=scan_id,
        symbol=clean_symbol,
        pick=pick.model_copy(update={"symbol": clean_symbol}),
        activated_at=utc_now(),
        status="active",
    )
    replaced = False
    for index, record in enumerate(records):
        if record.symbol.upper() == clean_symbol:
            records[index] = next_record
            replaced = True
            break
    if not replaced:
        records.append(next_record)
    write_active(records, day=day)
    return next_record
