# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**INDIE_MARKET_ANALYST** — a tool-first, swarm-orchestrated Indian-market analyst built on the `openai-agents` SDK (PyPI) with OpenRouter as the LLM provider. Free data sources only (yfinance, mcxlib/MCX India, Google Finance scrape, NSE/BSE public endpoints).

## Commands

Python (uv-managed):

```bash
uv sync                                             # install / resync deps
uv run pytest                                       # run all tests
uv run pytest tests/test_swarm_topology.py          # single file
uv run pytest tests/test_metrics.py::test_drawdown_sign  # single test
uv run ruff check .                                 # lint
uv run uvicorn indie_market_analyst.api_server:app --reload    # API (SSE chat)
uv run indie-analyst chat                           # Rich CLI REPL
uv run indie-analyst tools                          # list discovered tools
uv run indie-analyst teams                          # list swarm teams
```

Frontend (Vite/React):

```bash
cd frontend && npm i && npm run dev                 # dev server on :5173 (proxies to API on :8000)
```

`.env` needs `OPENROUTER_API_KEY` (see `.env.example`).

## Architecture — the parts you can't see from a single file

The system has **two independent planes**:

1. **Cognitive engine** (`indie_market_analyst/`) — everything LLM-facing. Agents, tools, skills, swarm orchestration, memory.
2. **Deterministic engine** (`backtest/`) — pure pandas/numpy. Agents call into it via tools; it never calls agents.

### Swarm = YAML topology → live `Agent` graph

Teams live as `config/swarm/*.yaml`. Each YAML declares agents (`name`, `role`, `tools`, `skills`, `handoffs`, `output_type`). `swarm/dispatcher.py:build_team` walks the spec, constructs `Agent` objects leaf-first (so parents can reference children), then wires handoffs via `agents.handoff(...)`. **Adding a new team is YAML-only** — no code change.

The canonical pipeline is `config/swarm/eod_report_pipeline.yaml`:
`orchestrator → collector → verifier → calculator → report_writer`, each agent constrained to a typed `output_type` from `core/schemas.py` so handoffs carry Pydantic payloads instead of free text.

### Model selection is config-driven

`providers/registry.py` reads `config/models.yaml` and returns a `LitellmModel` via `providers/openrouter.py`. Role strings in swarm YAML (`role: collector`) map to OpenRouter slugs (`anthropic/claude-sonnet-4`, etc.). Swap a role's model by editing `config/models.yaml` — no code change.

### Tool discovery is reflection-based

`tools/registry.py` walks `indie_market_analyst.tools.*` and harvests any module-level `TOOLS: list[Tool]`. Every tool is a `@function_tool`-decorated callable returning a Pydantic model. Swarm YAML references tools by name; the registry resolves them. **To add a tool:** drop a module under `tools/<category>/`, export `TOOLS = [...]`. No registration step.

### Skills are ephemeral prompt fragments

A skill is `skills/<name>/` containing `SKILL.md` + `meta.yaml` (triggers, optional tool allowlist, optional `output_type`, optional `templates/`). `skills/registry.py:discover` loads them; `swarm/dispatcher.py` concatenates `SKILL.md` into an agent's `instructions` when the agent's YAML lists `skills: [<name>]`. The `report_writer` skill is the reference example — it owns the PDF Jinja2 template.

### Hallucination control is a 3-layer stack

1. **Structured outputs:** every specialist agent has `output_type=<Pydantic>` — no free text between hops.
2. **Verifier agent** (in the swarm): cross-checks `CollectorOutput.points` for source/recency/finiteness.
3. **`guardrails/tool_first.py`** output guardrail: regex-detects numeric claims and trips when no tool was called that turn. The run context's `context["tool_calls"]` list is the signal.

Always keep these three in mind when adding agents or tools — a new tool that returns numbers should flow through a typed schema and be referenced by downstream agents, not pasted into free-form text.

### Runtime loop

`agent/orchestrator.py:run_turn` is the only entry point callers (api_server, cli) use. It:
1. picks a team via `agent/router.py:pick_team` (keyword rules),
2. builds the team (`swarm.dispatcher.load_and_build`),
3. runs `Runner.run_streamed(root_agent, input=text, context={"tool_calls": [...]})`,
4. normalizes SDK stream events to `StreamEvent(kind, data)` (delta | tool_call | handoff | final | error),
5. decorates the final markdown with disclaimer + timestamp (`guardrails/disclaimer.py`),
6. persists user + assistant messages to SQLite via `memory/store.py`.

### Persistence

Single SQLite file at `sessions/memory.db` (path from `DB_PATH` env). Tables: `sessions`, `messages`, `observations` (long-term memory, tag-indexed), `runs` (backtest/report JSON blobs). `memory/store.py:get_store()` is the singleton. Per-session asyncio locks live in `session/manager.py` to prevent concurrent-turn corruption of the in-memory scratchpad (`memory/short_term.py`).

### Backtest engine contract

`backtest/runner.py:run(symbol, signals, ...)` is the public entry. `signals` is a `pd.Series ∈ {-1,0,1}` aligned to loader index. `engines/equity_engine.py` is vectorized, applies the Indian cost model (`engines/_market_hooks.py`: STT, stamp duty, exchange txn, SEBI fee, GST, Zerodha-style brokerage with ₹20/side cap). `metrics.py` emits Sharpe/Sortino/MaxDD/annualized vol. Loaders self-register via `loaders/registry.register(name, fn)`.

## Conventions worth preserving

- Every Pydantic schema between agents uses `ConfigDict(extra="forbid")` (see `core/schemas.py:_Strict`). Don't loosen this — it forces correct tool outputs.
- DataPoints carry `source` + `as_of`. Tools must populate both so the Verifier can judge freshness.
- Frontend routes `/market`, `/options`, `/fno` are **intentionally** placeholder pages. The build-out plan defers them; don't wire real charts there without approval.
- `agents.Runner.run_streamed` signature differs subtly across SDK versions. If you touch `orchestrator._normalize`, verify event `type` names against the installed `openai-agents` version.
