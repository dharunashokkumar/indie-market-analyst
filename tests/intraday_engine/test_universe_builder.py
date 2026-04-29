from __future__ import annotations

from intraday_engine.universe import builder
from intraday_engine.universe.custom_csv import row_from_symbol


def test_list_universes_reports_static_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "CUSTOM_CSV_PATH", tmp_path / "missing_custom.csv")

    rows = builder.list_universes()
    by_id = {row.id: row for row in rows}

    assert by_id["nifty50"].size == 50
    assert by_id["nifty200"].size == 200
    assert by_id["nifty500"].size == 500
    assert by_id["fno"].size > 100
    assert by_id["full_nse"].size > 2000
    assert by_id["custom_csv"].available is False


def test_build_universe_merges_top_movers_without_duplicates(monkeypatch):
    extra = row_from_symbol("ZZZTEST", name="Synthetic Test", source="test")
    duplicate = row_from_symbol("RELIANCE", name="Duplicate Reliance", source="test")
    assert extra is not None
    assert duplicate is not None
    monkeypatch.setattr(builder, "fetch_top_movers", lambda: [duplicate, extra])

    universe = builder.build_universe("nifty50")
    symbols = [row.symbol for row in universe.symbols]

    assert universe.base_count == 50
    assert universe.total_count == 51
    assert symbols.count("RELIANCE") == 1
    assert "ZZZTEST" in symbols
