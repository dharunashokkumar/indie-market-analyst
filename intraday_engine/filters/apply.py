"""Composable filters for intraday scan universes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intraday_engine.data_sources.base import Candle, QuoteSnapshot, SurveillanceEntry
from intraday_engine.filters.asm_gsm import load_tags, tags_by_symbol
from intraday_engine.filters.liquidity import (
    MIN_DAILY_TURNOVER_RUPEES,
    LiquidityDecision,
    check_liquidity,
)
from intraday_engine.universe.builder import BuiltUniverse, UniverseSymbol

QuoteProvider = Callable[[str], QuoteSnapshot]


class FilteredSymbol(UniverseSymbol):
    asm_gsm_tags: list[str] = Field(default_factory=list)
    turnover: float | None = None


class FilterRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    reason: str
    stage: str
    detail: str = ""
    turnover: float | None = None


class FilterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[FilteredSymbol] = Field(default_factory=list)
    rejected: list[FilterRejection] = Field(default_factory=list)
    input_count: int
    output_count: int
    asm_gsm_tagged_count: int = 0
    min_turnover: float = MIN_DAILY_TURNOVER_RUPEES


def apply_filters(
    universe: BuiltUniverse | Sequence[UniverseSymbol | Mapping[str, Any] | str],
    *,
    quotes: Mapping[str, QuoteSnapshot] | None = None,
    candles_by_symbol: Mapping[str, Sequence[Candle]] | None = None,
    quote_provider: QuoteProvider | None = None,
    asm_gsm_entries: Sequence[SurveillanceEntry] | None = None,
    asm_gsm_tags: Mapping[str, Sequence[str]] | None = None,
    min_turnover: float = MIN_DAILY_TURNOVER_RUPEES,
    enforce_liquidity: bool = True,
) -> FilterResult:
    """Apply ASM/GSM tagging and the turnover floor in one pass."""
    symbols = _normalize_universe(universe)
    tags = _resolve_tags(asm_gsm_entries=asm_gsm_entries, asm_gsm_tags=asm_gsm_tags)
    kept: list[FilteredSymbol] = []
    rejected: list[FilterRejection] = []

    for symbol in symbols:
        clean_symbol = symbol.symbol.upper()
        quote = _quote_for(clean_symbol, quotes, quote_provider)
        candles = (candles_by_symbol or {}).get(clean_symbol)
        liquidity = check_liquidity(
            clean_symbol,
            quote=quote,
            candles=candles,
            min_turnover=min_turnover,
        )
        if enforce_liquidity and not liquidity.passed:
            rejected.append(_liquidity_rejection(liquidity))
            continue
        kept.append(
            FilteredSymbol(
                **symbol.model_dump(),
                asm_gsm_tags=list(tags.get(clean_symbol, [])),
                turnover=liquidity.turnover,
            )
        )

    return FilterResult(
        symbols=kept,
        rejected=rejected,
        input_count=len(symbols),
        output_count=len(kept),
        asm_gsm_tagged_count=sum(1 for item in kept if item.asm_gsm_tags),
        min_turnover=min_turnover,
    )


def _normalize_universe(
    universe: BuiltUniverse | Sequence[UniverseSymbol | Mapping[str, Any] | str],
) -> list[UniverseSymbol]:
    raw_symbols = universe.symbols if isinstance(universe, BuiltUniverse) else list(universe)
    out: list[UniverseSymbol] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        symbol = _normalize_symbol(raw)
        clean_symbol = symbol.symbol.upper()
        if clean_symbol in seen:
            continue
        seen.add(clean_symbol)
        out.append(symbol.model_copy(update={"symbol": clean_symbol}))
    return out


def _normalize_symbol(raw: UniverseSymbol | Mapping[str, Any] | str) -> UniverseSymbol:
    if isinstance(raw, UniverseSymbol):
        return raw
    if isinstance(raw, str):
        symbol = raw.strip().upper()
        return UniverseSymbol(symbol=symbol, yahoo_symbol=f"{symbol}.NS", name=symbol)
    data = dict(raw)
    symbol = str(data.get("symbol") or "").strip().upper()
    data.setdefault("yahoo_symbol", f"{symbol}.NS")
    data.setdefault("name", symbol)
    data.setdefault("series", "EQ")
    data.setdefault("isin", "")
    data.setdefault("industry", "")
    data.setdefault("source", "")
    data.setdefault("as_of", "")
    data["symbol"] = symbol
    return UniverseSymbol.model_validate(data)


def _resolve_tags(
    *,
    asm_gsm_entries: Sequence[SurveillanceEntry] | None,
    asm_gsm_tags: Mapping[str, Sequence[str]] | None,
) -> dict[str, list[str]]:
    if asm_gsm_tags is not None:
        return {key.upper(): list(value) for key, value in asm_gsm_tags.items()}
    if asm_gsm_entries is not None:
        return tags_by_symbol(list(asm_gsm_entries))
    return load_tags()


def _quote_for(
    symbol: str,
    quotes: Mapping[str, QuoteSnapshot] | None,
    quote_provider: QuoteProvider | None,
) -> QuoteSnapshot | None:
    if quotes is not None and symbol in quotes:
        return quotes[symbol]
    if quote_provider is None:
        return None
    try:
        return quote_provider(symbol)
    except Exception:
        return None


def _liquidity_rejection(decision: LiquidityDecision) -> FilterRejection:
    return FilterRejection(
        symbol=decision.symbol,
        reason=decision.reason,
        stage="liquidity",
        detail=f"turnover must be at least {decision.threshold:.0f}",
        turnover=decision.turnover,
    )
