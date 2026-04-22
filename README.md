# indie-market-analyst

**The open-source, hallucination-resistant AI research analyst for Indian Stock Markets (NSE & BSE).**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

> **Live Documentation:** [indiemarket.dharunashokkumar.com](https://indiemarket.dharunashokkumar.com)

indie-market-analyst is a tool-first, swarm-orchestrated intelligence engine designed to eliminate LLM hallucinations in financial research. It provides automated technical analysis, fundamental data collection, and a deterministic backtester specifically calibrated for the Indian market cost model (STT, GST, and brokerage).

---

## What it is

A hallucination-resistant analyst for Indian markets. Ask "what's the setup on JSWSTEEL?" and a swarm of specialist agents — collector, verifier, calculator, writer — fan out, pull numbers from tools, cross-check freshness and sources, and return a Pydantic-typed note instead of free-form prose.

Built on the [`openai-agents` SDK](https://github.com/openai/openai-agents-python) with OpenRouter as the LLM provider (free tier by default).

## Why it exists

Most "financial LLM" demos happily hallucinate closing prices. This project inverts the default:

- Agents may only talk about numbers they pulled from a verified tool call on this turn.
- An output guardrail rejects free-floating figures.
- Every handoff between agents carries a **strict** Pydantic schema (`extra="forbid"`).
- A dedicated verifier agent cross-checks source + recency on every data point.

## Features

- **Swarm orchestration.** Teams live as `config/swarm/*.yaml` — add a team, declare agents, wire handoffs. No code change.
- **Tool-first design.** Reflection-based registry: drop a module under `tools/<category>/`, export `TOOLS = [...]`, done.
- **Free data.** yfinance, NSE/BSE public endpoints, Google Finance scrape.
- **Deterministic backtester.** Pure pandas/numpy with Indian cost model (STT, stamp duty, exchange txn, SEBI fee, GST, Zerodha-style brokerage).
- **Transparent reasoning.** UI exposes tool calls with args + result + duration, handoffs, and an optional reasoning drawer.
- **Multi-model.** OpenRouter-backed; roles map to models in `config/models.yaml`.
- **Memory.** SQLite-backed sessions + messages + runs, with a sidebar of past chats and keyword search.

## Quickstart

```bash
# Python side
uv sync
cp .env.example .env          # add OPENROUTER_API_KEY
uv run uvicorn indie_market_analyst.api_server:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. Ask: _"what's the setup on JSWSTEEL?"_

CLI alternative:

```bash
uv run indie-analyst chat
uv run indie-analyst tools    # list discovered tools
uv run indie-analyst teams    # list swarm teams
```

## Documentation map

- **Live docs:** [indiemarket.dharunashokkumar.com](https://indiemarket.dharunashokkumar.com)
- **Local docs pages:** `docs/index.html`, `docs/quickstart.html`, `docs/architecture.html`
- **Contributor guide:** [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- **Architecture deep-dive:** [`CLAUDE.md`](./CLAUDE.md)

To preview the static docs locally:

```bash
python3 -m http.server 4173 -d docs
```

Then open `http://localhost:4173`.

## Architecture

Two independent planes:

1. **Cognitive engine** (`indie_market_analyst/`) — agents, tools, skills, swarm dispatcher, memory.
2. **Deterministic engine** (`backtest/`) — pure pandas/numpy. Agents call into it via tools; it never calls agents.

Typical flow:

```text
user → FastAPI /chat/stream (SSE)
     → orchestrator.run_turn
     → router picks a team
     → swarm.dispatcher builds Agent graph from YAML
     → Runner.run_streamed → normalized events
     → final Pydantic note → markdown → UI
```

The canonical pipeline is `config/swarm/eod_report_pipeline.yaml`:
`orchestrator → collector → verifier → calculator → report_writer`.

See `CLAUDE.md` for the architectural deep-dive and `CONTRIBUTING.md` for setup.

## Layout

```text
indie_market_analyst/
  agent/  core/  memory/  session/  providers/
  tools/  skills/  swarm/  guardrails/
  api_server.py  cli.py
config/swarm/*.yaml         # team topologies
config/models.yaml          # model lineup per role
backtest/                   # loaders, engines, optimizers, metrics
frontend/                   # Vite + React SPA
docs/                       # landing page (GitHub Pages)
runs/  sessions/            # audit trail (gitignored)
tests/
```

## Roadmap

Phase 1 (shipped):

- Hallucination fix: typed agent outputs, verifier, tool-first guardrail, clean streaming normalizer.
- UI: chat with sidebar, thinking drawer, tool cards, theme toggle, session search.
- OSS scaffolding: CI, Docker, Makefile, contribution docs.
- Landing page.

Phase 2 (planned):

- Dashboards: portfolio equity curve, Nifty/BankNifty/sector heatmaps, backtest result views.
- Portfolio / investment management: CSV upload, concentration & sector exposure, rebalancing suggestions.
- More intraday strategies: opening-range breakout, VWAP pullback, supertrend, SMA crossover.
- Playwright scraping tools: moneycontrol/livemint news, Groww authenticated order/holdings sync.

## Disclaimer

This is **research tooling**, not investment advice. Numbers are as accurate as free sources permit. Verify before trading.

## License

MIT. See [LICENSE](./LICENSE).
