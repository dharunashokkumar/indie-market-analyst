# CLAUDE.md

This file provides maintainer guidance for Claude Code (claude.ai/code) when working in this repository.

## Project

**INDIE_MARKET_ANALYST** is an Indian-market analysis toolkit. It includes a deterministic intraday scanner, market dashboards, strategy and backtest tooling, instrument data APIs, and an optional AI-assisted chat built on the `openai-agents` SDK with OpenRouter.

The old single-feature AI positioning is no longer the whole product. Treat AI chat as one feature. Do not make deterministic market workflows depend on LLM calls.

## Commands

Python:

```bash
uv sync
uv run pytest
uv run pytest tests/intraday_engine/
uv run pytest tests/test_swarm_topology.py
uv run pytest tests/test_metrics.py::test_drawdown_sign
uv run ruff check .
uv run uvicorn indie_market_analyst.api_server:app --reload
uv run indie-analyst chat
uv run indie-analyst tools
uv run indie-analyst teams
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
```

`.env` needs `OPENROUTER_API_KEY` only for the AI chat feature. Intraday, dashboard, and backtest work can usually be developed without an LLM key.

## Architecture

The repo has five important planes:

1. **API gateway** (`indie_market_analyst/api_server.py`) - FastAPI routes for chat, sessions, runs, strategy, dashboards, market data, and intraday.
2. **Intraday engine** (`intraday_engine/`) - deterministic scanner workflows, modes, candle sources, filters, detectors, scoring, JSON storage, and `/intraday/*` routes.
3. **Backtest engine** (`backtest/`) - pandas/numpy loaders, strategies, scans, trades, cost model, metrics, and optimizers.
4. **AI chat feature** (`indie_market_analyst/agent`, `tools`, `swarm`, `skills`, `guardrails`) - optional OpenRouter-backed chat with typed tools and guarded outputs.
5. **Frontend** (`frontend/`) - Vite + React app with Chat, Dashboards, Strategy, and Intraday sections.

### Intraday engine

`intraday_engine/api/routes.py` mounts under `/intraday`. The major routes are:

- `GET /intraday/mode`
- `GET/PUT /intraday/settings`
- `GET /intraday/universes`
- `POST /intraday/universes/custom-csv`
- `POST /intraday/scan`
- `GET /intraday/scan/{scan_id}`
- `GET /intraday/picks/today`
- `GET/POST /intraday/picks/active`
- `GET /intraday/symbol/{symbol}`
- `GET /intraday/chart/{symbol}`
- `GET /intraday/premarket/today`
- `GET /intraday/preopen/today`
- `GET /intraday/postmarket/today`
- `GET /intraday/weekend/this`

The live scan flow is:

```text
request
  -> ist_clock.mode_context
  -> universe.builder.build_universe + top movers
  -> data_sources.router + candle cache
  -> filters.apply
  -> detectors.run_all
  -> scoring.direction/probability/conviction
  -> storage.picks JSON
  -> typed ScanResult
```

Important intraday rules:

- Keep scanner output deterministic and compact: symbol, direction, probability, conviction, detectors, volume context, price context, source, and freshness.
- Do not add stop-loss, target, or entry-zone fields unless the user explicitly changes that requirement.
- Keep intraday persistence as JSON under `data/intraday/`. Do not move it to SQLite.
- NSE direct is the primary source; yfinance is the fallback. The settings page must keep cookie/source changes runtime-configurable.
- ASM/GSM should tag picks, not automatically reject them.
- The detector set currently includes ORB, VWAP reclaim, breakout, flag, momentum, and short-cover proxy.

### Backtest engine

`backtest/runner.py:run` is the public entry for deterministic runs. Signals are a `pd.Series` in `{-1, 0, 1}` aligned to the loader index. `backtest/engines/equity_engine.py` applies the Indian cost model from `backtest/engines/_market_hooks.py`: STT, stamp duty, exchange transaction charges, SEBI fee, GST, and Zerodha-style brokerage with a 20 INR per-side cap.

Strategies live under `backtest/strategies/` and register through the strategy registry. Metrics live in `backtest/metrics.py`. Runs are persisted through the SQLite-backed store used by dashboard panels.

### AI chat

The AI feature remains useful but should be treated as optional.

Teams live as `config/swarm/*.yaml`. Each YAML declares agents (`name`, `role`, `tools`, `skills`, `handoffs`, `output_type`). `indie_market_analyst/swarm/dispatcher.py:build_team` constructs `Agent` objects leaf-first and wires handoffs via `agents.handoff(...)`. Adding or changing a team should usually be YAML-only.

Model selection is config-driven. `providers/registry.py` reads `config/models.yaml` and returns a `LitellmModel` via `providers/openrouter.py`. Role strings in swarm YAML map to OpenRouter slugs. Swap a role's model by editing `config/models.yaml`.

Tool discovery is reflection-based. `tools/registry.py` walks `indie_market_analyst.tools.*` and harvests module-level `TOOLS: list[Tool]`. A new tool should be a `@function_tool` callable returning a strict Pydantic model. Tools that return numbers should include source and freshness fields where applicable.

Skills live under `indie_market_analyst/skills/<name>/` with `SKILL.md` and `meta.yaml`. The dispatcher concatenates a skill's `SKILL.md` into agent instructions when YAML lists `skills: [<name>]`.

Hallucination control has three layers:

1. Structured outputs with strict Pydantic schemas between specialist agents.
2. Verifier agents that check source, recency, and finite numeric values.
3. `guardrails/tool_first.py`, which rejects unsupported numeric claims when no tool call produced data for the turn.

### Runtime chat loop

`agent/orchestrator.py:run_turn` is the chat entry point used by the API and CLI:

1. `agent/router.py:pick_team` selects a team.
2. `swarm.dispatcher.load_and_build` builds the agent graph.
3. `Runner.run_streamed` streams SDK events.
4. The orchestrator normalizes events to `StreamEvent(kind, data)`.
5. `guardrails/disclaimer.py` decorates final chat output.
6. `memory/store.py` persists the user and assistant messages to SQLite.

### Persistence

- Chat sessions, messages, observations, and run blobs use SQLite at `sessions/memory.db` unless `DB_PATH` overrides it.
- Intraday settings, candle cache, scans, active picks, reviews, premarket snapshots, and weekend snapshots use JSON under `data/intraday/`.
- `runs/` and `sessions/` are local audit/persistence paths and should remain gitignored except `.gitkeep`.

## Frontend map

- `frontend/src/router.tsx` wires the SPA routes.
- `frontend/src/pages/ChatPage.tsx` is the AI chat.
- `frontend/src/pages/DashboardsPage.tsx` hosts Market, Equity, Backtests, and Heatmap panels.
- `frontend/src/pages/StrategyPage.tsx` runs deterministic strategies across supported instrument groups.
- `frontend/src/pages/Intraday/` contains the seven intraday modes plus settings and shared components.
- `frontend/src/lib/api.ts` owns backend client functions and shared response types.

## Conventions worth preserving

- Keep deterministic logic out of prompts.
- Keep Pydantic schemas strict with `ConfigDict(extra="forbid")` for agent handoffs and API models where that is already the pattern.
- Data points should carry `source` and `as_of` when the UI or verifier needs freshness.
- Use structured parsers and typed models instead of ad hoc string handling for source data.
- Do not turn placeholder or planned pages into major features without checking the current scope.
- When touching `orchestrator._normalize`, verify SDK event `type` names against the installed `openai-agents` version.
