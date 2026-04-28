from indie_market_analyst.data.nse_universe import load_nse_universe, search


def test_universe_loads_with_min_rows():
    df = load_nse_universe()
    assert len(df) >= 1500
    assert {"symbol", "yahoo_symbol", "name"}.issubset(df.columns)


def test_universe_yahoo_suffix():
    df = load_nse_universe()
    assert (df["yahoo_symbol"].str.endswith(".NS")).all()


def test_search_reliance_prefix_first():
    rows = search("reliance", limit=10)
    assert rows, "expected at least one match for 'reliance'"
    assert any(r["symbol"] == "RELIANCE" for r in rows)
    # Symbol-prefix should rank first
    assert rows[0]["symbol"].lower().startswith("reliance")


def test_search_by_symbol_exact():
    rows = search("TCS", limit=5)
    assert rows[0]["symbol"] == "TCS"
    assert rows[0]["yahoo_symbol"] == "TCS.NS"


def test_search_empty_returns_head():
    rows = search("", limit=5)
    assert len(rows) == 5
