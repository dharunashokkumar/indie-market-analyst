"""Mode 3 last-hour scan wrapper."""

from __future__ import annotations

from intraday_engine.modes.live_scan import LiveScanRequest, run_live_scan
from intraday_engine.output_schema import ScanResult

LAST_HOUR_MIN_VOLUME_X_AVG = 4.0
LAST_HOUR_MIN_PROBABILITY = 0.45
LAST_HOUR_TOP_PICK_LIMIT = 5
LAST_HOUR_WATCH_ONLY_LIMIT = 12


def run_last_hour_scan(request: LiveScanRequest | None = None) -> ScanResult:
    base = request or LiveScanRequest()
    tightened = base.model_copy(
        update={
            "mode_override": "3",
            "min_volume_x_avg": max(base.min_volume_x_avg, LAST_HOUR_MIN_VOLUME_X_AVG),
            "min_probability": max(base.min_probability, LAST_HOUR_MIN_PROBABILITY),
            "top_pick_limit": min(base.top_pick_limit, LAST_HOUR_TOP_PICK_LIMIT),
            "watch_only_limit": min(base.watch_only_limit, LAST_HOUR_WATCH_ONLY_LIMIT),
        }
    )
    return run_live_scan(tightened)
