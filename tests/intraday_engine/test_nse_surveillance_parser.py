from __future__ import annotations

from intraday_engine.data_sources.nse_direct import NseDirectSource


def test_nse_direct_parses_current_asm_gsm_reports(monkeypatch):
    source = NseDirectSource()

    def fake_get_json(path, params=None):
        if path == "/api/reportASM":
            return {
                "longterm": {
                    "data": [
                        {
                            "symbol": "AAREYDRUGS",
                            "asmSurvIndicator": "Stage I",
                            "survCode": "LTASM - I (13)",
                        }
                    ]
                },
                "shortterm": {"data": [{"symbol": "ABC", "survCode": "STASM - I (9)"}]},
            }
        if path == "/api/reportGSM":
            return [{"symbol": "ASIL", "gsmStage": "VI", "survCode": "GSM - VI (6)"}]
        raise AssertionError(path)

    monkeypatch.setattr(source, "_get_json", fake_get_json)

    rows = source.fetch_asm_gsm()
    by_symbol = {row.symbol: row for row in rows}

    assert by_symbol["AAREYDRUGS"].list_type == "ASM"
    assert by_symbol["AAREYDRUGS"].stage == "LTASM - I (13)"
    assert by_symbol["ABC"].raw["term"] == "shortterm"
    assert by_symbol["ASIL"].list_type == "GSM"
    assert by_symbol["ASIL"].stage == "GSM - VI (6)"
