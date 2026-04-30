# Contributing to indie-market-analyst

Thanks for considering a contribution. This project is an Indian-market analysis toolkit with deterministic scanners, dashboards, backtesting, data tools, and an optional AI-assisted chat. Keep changes small, source-backed, and consistent with the existing module boundaries.

## Ground rules

- Python 3.12+, managed with `uv`.
- Node/Vite frontend lives in `frontend/`.
- Defaults should use free public data sources and free-tier models where models are needed. Paid providers can be added only as explicit opt-in paths.
- Deterministic market features should not depend on an LLM. Put scanner, strategy, and backtest logic in normal Python modules with tests.
- User-facing copy must not present output as investment advice or guaranteed trade guidance.
- No `Co-Authored-By: Claude` in commits or PR descriptions.

## Local setup

```bash
uv sync
cp .env.example .env
uv run pytest
uv run ruff check .
uv run uvicorn indie_market_analyst.api_server:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

`OPENROUTER_API_KEY` is needed for `/chat`. Intraday and backtest work can usually be developed without it.

## Project areas

- `intraday_engine/` owns the deterministic intraday scanner, source routing, filters, detectors, scoring, mode runners, and JSON storage.
- `backtest/` owns loaders, strategies, engines, optimizers, metrics, scans, and trade derivation.
- `indie_market_analyst/api_server.py` is the FastAPI gateway for chat, sessions, dashboards, runs, strategy, market data, and intraday routes.
- `indie_market_analyst/tools/`, `config/swarm/`, and `indie_market_analyst/skills/` power the optional AI chat.
- `frontend/src/pages/` owns the React surfaces: Chat, Dashboards, Strategy, and Intraday.

## Adding intraday scanner logic

1. Put data-source code under `intraday_engine/data_sources/`.
2. Put universe logic under `intraday_engine/universe/`.
3. Put reusable filters under `intraday_engine/filters/`.
4. Put setup detectors under `intraday_engine/detectors/`.
5. Put score/ranking changes under `intraday_engine/scoring/`.
6. Add or update tests under `tests/intraday_engine/`.

Intraday output should stay minimal and deterministic: direction, probability, conviction, detector evidence, volume context, price context, and freshness/source metadata. Do not add stop-loss, target, or entry-zone fields unless that requirement is explicitly changed.

## Adding a backtest strategy

1. Create the strategy module under `backtest/strategies/`.
2. Register it through the existing strategy registry.
3. Return deterministic signal series aligned to the loader output.
4. Add tests for signal generation, metrics, and edge cases.
5. Confirm costs still flow through the Indian cost model rather than being reimplemented ad hoc.

## Adding an API route

- Prefer mounting routes through the smallest owning module. Intraday routes belong in `intraday_engine/api/routes.py`.
- Keep response models typed with Pydantic.
- Return source and freshness metadata where the caller displays market data.
- Avoid blocking long-running work in request handlers unless the existing route already follows that pattern.

## Adding an AI chat tool

1. Create `indie_market_analyst/tools/<category>/<name>.py`.
2. Decorate the callable with `@function_tool` from the Agents SDK.
3. Return a strict Pydantic model carrying `source` and `as_of` where applicable.
4. Export `TOOLS: list[Tool]` at module level. The reflection registry picks it up automatically.
5. Add focused tests for the tool and any parsing logic.

Every Pydantic schema exchanged between agents should keep `ConfigDict(extra="forbid")`.

## Adding an AI skill or team

Skills live under `indie_market_analyst/skills/<name>/` and contain:

- `SKILL.md`: prompt fragment appended to an agent's instructions.
- `meta.yaml`: triggers, optional tool allowlist, optional `output_type`.

Reference the skill by name from a swarm YAML under `skills: [<name>]`.

Teams live under `config/swarm/`. Declare agents, `role`, `tools`, `skills`, `handoffs`, and `output_type`. The dispatcher walks the spec, so most team changes should be YAML-only.

## Testing

- Unit tests live under `tests/`. Keep them fast and deterministic.
- Intraday detectors and scoring have focused tests in `tests/intraday_engine/`.
- Backtest logic should be tested without the AI chat loop.
- Orchestrator stream normalization has dedicated fake-event tests in `tests/test_orchestrator_normalize.py`.

Run the relevant checks before opening a PR:

```bash
uv run pytest
uv run ruff check .
cd frontend && npm run build
```

## Pull requests

- Describe the user-facing change and the module touched.
- Include screenshots for UI-affecting changes.
- Include tests for scanner, strategy, parsing, or API behavior.
- Keep unrelated formatting churn out of functional PRs.

## Security

Do not open public issues for security reports. See `SECURITY.md`.
