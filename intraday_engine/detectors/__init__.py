"""Setup detectors for the intraday scanner."""

from intraday_engine.detectors.base import DETECTOR_NAMES, DetectorResult, run_all_detectors

__all__ = ["DETECTOR_NAMES", "DetectorResult", "run_all_detectors"]
