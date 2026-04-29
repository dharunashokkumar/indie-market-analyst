from __future__ import annotations

import sys
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.loaders import mcx_loader


def _raw_mcx_rows() -> pd.DataFrame:
    """Two trade days, two GOLD FUTCOM expiries far outside the roll window,
    plus an OPTCOM row that must be filtered out and a SILVER row that
    must be ignored when querying GOLD."""
    return pd.DataFrame(
        [
            {
                "Date": "2024-06-03",
                "Symbol": "GOLD",
                "Instrument Name": "FUTCOM",
                "Expiry Date": "2024-08-05",
                "Open": "71,000",
                "High": "71,500",
                "Low": "70,900",
                "Close": "71,250",
                "Volume": "120",
            },
            {
                "Date": "2024-06-03",
                "Symbol": "GOLD",
                "Instrument Name": "FUTCOM",
                "Expiry Date": "2024-10-05",
                "Open": "71,300",
                "High": "71,700",
                "Low": "71,100",
                "Close": "71,600",
                "Volume": "500",
            },
            {
                "Date": "2024-06-04",
                "Symbol": "GOLD",
                "Instrument Name": "OPTCOM",
                "Expiry Date": "2024-08-05",
                "Open": "100",
                "High": "120",
                "Low": "90",
                "Close": "110",
                "Volume": "999",
            },
            {
                "Date": "2024-06-04",
                "Symbol": "GOLD",
                "Instrument Name": "FUTCOM",
                "Expiry Date": "2024-08-05",
                "Open": "71,200",
                "High": "71,800",
                "Low": "71,000",
                "Close": "71,700",
                "Volume": "130",
            },
            {
                "Date": "2024-06-04",
                "Symbol": "SILVER",
                "Instrument Name": "FUTCOM",
                "Expiry Date": "2024-08-05",
                "Open": "90,000",
                "High": "91,000",
                "Low": "89,500",
                "Close": "90,500",
                "Volume": "300",
            },
        ]
    )


def test_normalize_mcx_history_picks_near_month_per_trade_day():
    spec = mcx_loader.resolve_mcx_symbol("GOLD")
    assert spec is not None

    df = mcx_loader._normalize_mcx_history(_raw_mcx_rows(), spec, "1d")

    assert list(df.columns) == ["open", "high", "low", "close", "volume", "source"]
    # 2024-06-03: near-month is 2024-08-05 (lower volume), not 2024-10-05 (higher volume)
    assert df.loc[pd.Timestamp("2024-06-03")]["close"] == 71250
    assert df.loc[pd.Timestamp("2024-06-03")]["volume"] == 120
    # 2024-06-04: only one FUTCOM expiry remains; OPTCOM filtered out
    assert df.loc[pd.Timestamp("2024-06-04")]["close"] == 71700
    assert set(df["source"]) == {"mcxlib"}


def test_load_mcx_uses_mcx_symbol_aliases(monkeypatch):
    monkeypatch.setattr(mcx_loader, "_fetch_mcx_history", lambda start, end: _raw_mcx_rows())

    df = mcx_loader.load_mcx("gold", period="1mo", interval="1d")

    assert not df.empty
    assert float(df["close"].iloc[-1]) == 71700


def test_normalize_silver_does_not_silently_use_silvermic():
    """SILVER must return SILVER's own rows, not SILVERMIC's, even when
    SILVERMIC has higher volume. Aliases are for input resolution only."""
    spec = mcx_loader.resolve_mcx_symbol("SILVER")
    assert spec is not None

    raw = pd.DataFrame(
        [
            {
                "Date": "04/29/2026",
                "Symbol": "SILVER",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": "05MAY2026",
                "Open": "235000",
                "High": "236000",
                "Low": "234000",
                "Close": "235818",
                "Volume": "817",
            },
            {
                "Date": "04/29/2026",
                "Symbol": "SILVERMIC",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": "30JUN2026",
                "Open": "245000",
                "High": "246000",
                "Low": "244000",
                "Close": "245100",
                "Volume": "38127",
            },
            {
                "Date": "04/29/2026",
                "Symbol": "SILVER",
                "InstrumentName": "OPTFUT",
                "ExpiryDate": "26MAY2026",
                "Open": "1000",
                "High": "1200",
                "Low": "900",
                "Close": "1100",
                "Volume": "999999",
            },
        ]
    )

    df = mcx_loader._normalize_mcx_history(raw, spec, "1d")

    assert float(df["close"].iloc[-1]) == 235818
    assert float(df["volume"].iloc[-1]) == 817


def test_normalize_silvermic_returns_silvermic_when_requested_directly():
    spec = mcx_loader.resolve_mcx_symbol("SILVERMIC")
    assert spec is not None
    assert spec.symbol == "SILVERMIC"

    raw = pd.DataFrame(
        [
            {
                "Date": "04/29/2026",
                "Symbol": "SILVER",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": "05MAY2026",
                "Open": "235000",
                "High": "236000",
                "Low": "234000",
                "Close": "235818",
                "Volume": "817",
            },
            {
                "Date": "04/29/2026",
                "Symbol": "SILVERMIC",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": "30JUN2026",
                "Open": "245000",
                "High": "246000",
                "Low": "244000",
                "Close": "245100",
                "Volume": "38127",
            },
        ]
    )

    df = mcx_loader._normalize_mcx_history(raw, spec, "1d")

    assert float(df["close"].iloc[-1]) == 245100


def test_normalize_mcx_history_rolls_before_expiry():
    """When the soonest expiry is within the roll window and the next expiry
    has volume, the loader rolls forward."""
    spec = mcx_loader.resolve_mcx_symbol("GOLD")
    assert spec is not None
    # default roll window is 2 days
    assert spec.roll_days_before_expiry == 2

    trade_day = pd.Timestamp("2026-04-29")
    near_expiry = trade_day + timedelta(days=1)  # 1 day away → within roll window
    next_expiry = trade_day + timedelta(days=30)
    raw = pd.DataFrame(
        [
            {
                "Date": trade_day.strftime("%Y-%m-%d"),
                "Symbol": "GOLD",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": near_expiry.strftime("%Y-%m-%d"),
                "Open": "150000",
                "High": "150500",
                "Low": "149500",
                "Close": "150250",
                "Volume": "100",
            },
            {
                "Date": trade_day.strftime("%Y-%m-%d"),
                "Symbol": "GOLD",
                "InstrumentName": "FUTCOM",
                "ExpiryDate": next_expiry.strftime("%Y-%m-%d"),
                "Open": "151000",
                "High": "151500",
                "Low": "150700",
                "Close": "151200",
                "Volume": "50",
            },
        ]
    )

    df = mcx_loader._normalize_mcx_history(raw, spec, "1d")

    # rolled to next expiry even though it has lower volume
    assert float(df["close"].iloc[-1]) == 151200


def test_get_mcx_quote_normalizes_market_watch(monkeypatch):
    raw = pd.DataFrame(
        [
            {
                "Symbol": "GOLD",
                "ExpiryDate": "31DEC2099",
                "InstrumentName": "FUTCOM",
                "Unit": "10 GRMS",
                "Open": "150000",
                "High": "151000",
                "Low": "149500",
                "LTP": "150500",
                "PreviousClose": "150000",
                "PercentChange": "0.33",
                "Volume": "42",
                "OpenInterest": "1234",
            }
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "mcxlib",
        SimpleNamespace(
            get_market_watch=lambda: raw.copy(),
            get_bhav_copy=lambda trade_date, instrument: pd.DataFrame(
                [{"Date": "04/28/2026", "Symbol": "GOLD"}]
            ),
        ),
    )

    quote = mcx_loader.get_mcx_quote("gold")

    assert quote["symbol"] == "GOLD"
    assert quote["last_price"] == 150500
    assert quote["prev_close"] == 150000
    assert quote["change_pct"] == pytest.approx(0.0033, rel=1e-3)
    assert quote["source"] == "mcxlib"
    assert quote["expiry"] == "31DEC2099"
    assert quote["expiry_iso"] == "2099-12-31"
    assert quote["unit"] == "10 GRMS"
    assert quote["open_interest"] == 1234.0
    assert quote["instrument"] == "FUTCOM"
    assert quote["contract_symbol"] == "GOLD"


def test_get_mcx_quote_does_not_silently_use_silvermic(monkeypatch):
    """get_mcx_quote('SILVER') must return the SILVER row, not SILVERMIC's."""
    raw = pd.DataFrame(
        [
            {
                "Symbol": "SILVER",
                "ExpiryDate": "05MAY2026",
                "InstrumentName": "FUTCOM",
                "Unit": "1 KGS",
                "Open": "235000",
                "High": "236000",
                "Low": "234000",
                "LTP": "235818",
                "PreviousClose": "237345",
                "PercentChange": "-0.64",
                "Volume": "817",
                "OpenInterest": "10",
            },
            {
                "Symbol": "SILVERMIC",
                "ExpiryDate": "30JUN2026",
                "InstrumentName": "FUTCOM",
                "Unit": "1 KGS",
                "Open": "245000",
                "High": "246000",
                "Low": "244000",
                "LTP": "245100",
                "PreviousClose": "246829",
                "PercentChange": "-0.70",
                "Volume": "38127",
                "OpenInterest": "5000",
            },
            {
                "Symbol": "SILVER",
                "ExpiryDate": "26MAY2026",
                "InstrumentName": "OPTFUT",
                "Unit": "1 KGS",
                "Open": "1000",
                "High": "1200",
                "Low": "900",
                "LTP": "1100",
                "PreviousClose": "1000",
                "PercentChange": "10",
                "Volume": "999999",
                "OpenInterest": "1",
            },
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "mcxlib",
        SimpleNamespace(
            get_market_watch=lambda: raw.copy(),
            get_bhav_copy=lambda trade_date, instrument: pd.DataFrame(
                [{"Date": "04/29/2026", "Symbol": "SILVER"}]
            ),
        ),
    )

    quote = mcx_loader.get_mcx_quote("silver")

    assert quote["symbol"] == "SILVER"
    assert quote["last_price"] == 235818
    assert quote["prev_close"] == 237345
    assert quote["expiry"] == "05MAY2026"
    assert quote["instrument"] == "FUTCOM"


def test_get_mcx_quote_resolves_real_trade_date(monkeypatch):
    """as_of must reflect the bhav copy trade date, not literal date.today()."""
    raw_quote = pd.DataFrame(
        [
            {
                "Symbol": "GOLD",
                "ExpiryDate": "05JUN2026",
                "InstrumentName": "FUTCOM",
                "Unit": "10 GRMS",
                "Open": "150000",
                "High": "151000",
                "Low": "149500",
                "LTP": "150500",
                "PreviousClose": "150000",
                "PercentChange": "0.33",
                "Volume": "42",
                "OpenInterest": "1",
            }
        ]
    )

    today = date.today()

    def fake_bhav_copy(trade_date, instrument):
        # First call (today's date) fails; previous business day succeeds.
        if trade_date == today.strftime("%Y%m%d"):
            raise RuntimeError("no data yet")
        return pd.DataFrame([{"Date": "04/28/2026", "Symbol": "GOLD"}])

    monkeypatch.setitem(
        sys.modules,
        "mcxlib",
        SimpleNamespace(
            get_market_watch=lambda: raw_quote.copy(),
            get_bhav_copy=fake_bhav_copy,
        ),
    )
    # Clear bhav cache so the lookback runs fresh
    mcx_loader._BHAV_COPY_CACHE.clear()

    quote = mcx_loader.get_mcx_quote("GOLD")

    expected = (today - timedelta(days=1)).isoformat()
    assert quote["as_of"] == expected
    assert quote["as_of_estimated"] is False


def test_get_mcx_icomdex_keys_by_commodity(monkeypatch):
    raw = pd.DataFrame(
        [
            {
                "Instrument_Identifier": 572,
                "Instrument_Code": "MCXMCXGOLDEX",
                "Instrument_Display_Name": "MCX iCOMDEX Gold",
                "LTP": 37458.78,
                "Open": 37895.77,
                "High": 38098.68,
                "Low": 37397.94,
                "Close": 37721.53,
                "NetChange": -262.75,
                "PercentChange": -0.70,
            },
            {
                "Instrument_Identifier": 573,
                "Instrument_Code": "MCXMCXSILVDEX",
                "Instrument_Display_Name": "MCX iCOMDEX Silver",
                "LTP": 27747.74,
                "Open": 28102.84,
                "High": 28162.61,
                "Low": 27725.35,
                "Close": 28007.55,
                "NetChange": -259.81,
                "PercentChange": -0.93,
            },
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "mcxlib",
        SimpleNamespace(get_mcx_icomdex_indices=lambda: raw.copy()),
    )

    out = mcx_loader.get_mcx_icomdex()

    assert set(out.keys()) == {"GOLD", "SILVER"}
    assert out["GOLD"]["ltp"] == 37458.78
    assert out["GOLD"]["display_name"] == "MCX iCOMDEX Gold"
    assert out["SILVER"]["percent_change"] == pytest.approx(-0.93)
