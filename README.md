# indie-market-analyst

**Open-source Indian-market analysis toolkit for intraday scanning, dashboards, backtesting, and optional AI-assisted chat.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

> **Live documentation:** [indiemarket.dharunashokkumar.com](https://indiemarket.dharunashokkumar.com)

indie-market-analyst is a full-stack market workspace for NSE/BSE users. The repo now contains deterministic intraday scanners, market dashboards, strategy backtests, instrument data APIs, and an optional AI-assisted chat. The AI layer is useful, but it is one feature of the toolkit rather than the whole product.

## What it is

A local-first Indian-market analysis app with four main surfaces:

- **Intraday scanner.** Seven IST-aware modes for pre-market, pre-open, live scan, last-hour scan, post-market review, single-symbol analysis, active-pick updates, and weekend planning.
- **Dashboards.** Market overview, index and sector heatmaps, equity views, and persisted backtest runs.
- **Strategy workbench.** Run deterministic strategies against equities, commodities, indices, ETFs, mutual-fund proxies, and crypto pairs where supported by the configured data source.
- **AI-assisted chat.** A tool-first assistant built with typed agent handoffs, source-aware data tools, and guardrails against unsupported numeric claims.

## Features

- **Deterministic intraday engine.** `intraday_engine/` fetches candles, applies liquidity and ASM/GSM filters, runs ORB, VWAP reclaim, breakout, flag, momentum, and short-cover detectors, then scores qualified picks.
- **Configurable universes.** Nifty 50, Nifty 200, Nifty 500, F&O, full NSE cash, and custom CSV uploads. NSE top gainers, losers, and most-active lists can be merged into the selected universe.
- **Data-source routing.** NSE direct is the primary intraday source, with yfinance fallback. Settings live under `/intraday/settings`.
- **Charts and overlays.** The frontend uses lightweight-charts for candles plus VWAP, ORB levels, previous-day high/low, moving averages, volume MA, and pivots.
- **Backtester.** Pure pandas/numpy engine with the Indian cost model: STT, stamp duty, exchange transaction charges, SEBI fees, GST, and Zerodha-style brokerage.
- **Run persistence.** SQLite stores chat sessions and backtest/report blobs; intraday scans use JSON files under `data/intraday/`.
- **Extensible AI feature.** Agent teams live in `config/swarm/*.yaml`; tools are discovered from `indie_market_analyst/tools/`; skills live under `indie_market_analyst/skills/`.

## Quickstart

```bash
# Backend
uv sync
cp .env.example .env
uv run uvicorn indie_market_analyst.api_server:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Useful entry points:

- `/intraday` for the deterministic intraday scanner.
- `/dashboards` for market, equity, heatmap, and backtest dashboards.
- `/strategy` for strategy runs across supported instruments.
- `/chat` for the AI-assisted chat.

`OPENROUTER_API_KEY` is only required for the chat/agent feature. The deterministic scanner and backtest surfaces can be developed and tested without an LLM key, subject to data-source availability.

CLI alternatives:

```bash
uv run indie-analyst chat
uv run indie-analyst tools
uv run indie-analyst teams
```

## Documentation map

- **Live docs:** [indiemarket.dharunashokkumar.com](https://indiemarket.dharunashokkumar.com)
- **Quickstart:** `docs/quickstart.html`
- **Architecture:** `docs/architecture.html`
- **Intraday scanner:** `docs/intraday.html`
- **Dashboards and data:** `docs/dashboards.html`
- **Backtester:** `docs/backtester.html`
- **AI chat and tools:** `docs/swarm-and-tools.html`
- **Contributor guide:** [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- **Maintainer notes:** [`CLAUDE.md`](./CLAUDE.md)

To preview the static docs locally:

```bash
python3 -m http.server 4173 -d docs
```

Then open `http://localhost:4173`.

## Architecture

The application is split into independent planes:

1. **API shell** (`indie_market_analyst/api_server.py`) exposes chat, sessions, runs, market data, strategy, dashboard, and intraday routes.
2. **Intraday engine** (`intraday_engine/`) is deterministic Python for scanning, scoring, storage, NSE/yfinance routing, and mode-specific workflows.
3. **Backtest engine** (`backtest/`) is pure pandas/numpy for strategies, loaders, costs, trades, metrics, scans, and optimizers.
4. **AI chat feature** (`indie_market_analyst/agent`, `tools`, `swarm`, `skills`, `guardrails`) handles optional OpenRouter-backed chat.
5. **Frontend** (`frontend/`) is a Vite + React app with Chat, Dashboards, Strategy, and Intraday sections.

Intraday scan flow:

```text
Frontend /intraday
  -> POST /intraday/scan
  -> universe builder + top movers
  -> NSE/yfinance candle source + cache
  -> filters + setup detectors
  -> probability, direction, conviction
  -> JSON scan storage
  -> picks table + chart overlays
```

AI chat flow:

```text
Frontend /chat
  -> FastAPI /chat/stream
  -> router selects a YAML team
  -> swarm dispatcher builds agent graph
  -> tools fetch source-backed data
  -> verifier and guardrails check numeric claims
  -> markdown answer persisted to SQLite
```

## Layout

```text
indie_market_analyst/       # API, AI chat feature, tools, memory, skills
intraday_engine/            # deterministic intraday scanner and routes
backtest/                   # loaders, strategies, engines, optimizers, metrics
frontend/                   # Vite + React application
config/swarm/*.yaml         # optional AI team topologies
config/models.yaml          # OpenRouter model lineup for chat roles
data/intraday/              # settings, universes, JSON scans, caches
docs/                       # static GitHub Pages docs
runs/  sessions/            # local audit trail and SQLite memory (gitignored)
tests/
```

## Current status

- Intraday scanner routes and UI are implemented for the full seven-mode workflow.
- Dashboards include market, equity, heatmap, and backtest run panels.
- Strategy runs and backtest persistence are wired through the backend.
- The AI chat remains available as an optional feature with typed tools and guarded outputs.

## Roadmap

- Scheduled intraday scans with configurable cron jobs.
- Telegram delivery for selected intraday workflows.
- More scanners and strategy templates.
- Expanded authenticated broker/import integrations where they can remain opt-in.

## Disclaimer

This is market-analysis software, not investment advice. Free and public data sources can be delayed, incomplete, or temporarily unavailable. Verify outputs before trading.

## License

MIT. See [LICENSE](./LICENSE).
