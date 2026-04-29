"""Settings persistence for intraday data-source selection."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from intraday_engine.data_sources.base import SourceName
from intraday_engine.storage.paths import SETTINGS_PATH, ensure_intraday_dirs

UniverseName = Literal["nifty50", "nifty200", "nifty500", "fno", "full_nse", "custom_csv"]


class IntradaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_source: SourceName = "nse_direct"
    fallback_source: SourceName = "yfinance"
    nse_cookies: str = ""
    default_universe: UniverseName = "nifty500"
    auto_poll_interval_seconds: Literal[30, 60, 300, 900] = 60

    @field_validator("nse_cookies", mode="before")
    @classmethod
    def clean_cookies(cls, value: object) -> str:
        return str(value or "").strip()


class IntradayPublicSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_source: SourceName = "nse_direct"
    fallback_source: SourceName = "yfinance"
    nse_cookies_configured: bool = False
    default_universe: UniverseName = "nifty500"
    auto_poll_interval_seconds: Literal[30, 60, 300, 900] = 60


class IntradaySettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_source: SourceName | None = None
    fallback_source: SourceName | None = None
    nse_cookies: str | None = None
    default_universe: UniverseName | None = None
    auto_poll_interval_seconds: Literal[30, 60, 300, 900] | None = None

    @field_validator("nse_cookies", mode="before")
    @classmethod
    def clean_cookies(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()


DEFAULT_SETTINGS = IntradaySettings()


def public_settings(settings: IntradaySettings) -> IntradayPublicSettings:
    return IntradayPublicSettings(
        default_source=settings.default_source,
        fallback_source=settings.fallback_source,
        nse_cookies_configured=bool(settings.nse_cookies.strip()),
        default_universe=settings.default_universe,
        auto_poll_interval_seconds=settings.auto_poll_interval_seconds,
    )


def load_settings() -> IntradaySettings:
    ensure_intraday_dirs()
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS
    if not isinstance(data, dict):
        return DEFAULT_SETTINGS
    try:
        return IntradaySettings.model_validate(data)
    except ValueError:
        return DEFAULT_SETTINGS


def save_settings(settings: IntradaySettings) -> IntradaySettings:
    ensure_intraday_dirs()
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_PATH)
    return settings


def update_settings(update: IntradaySettingsUpdate) -> IntradaySettings:
    current = load_settings()
    changed = current.model_copy(update=update.model_dump(exclude_none=True))
    return save_settings(changed)
