.PHONY: install dev api frontend test lint fmt build docker-build docker-run clean seed-runs

install:
	uv sync
	cd frontend && npm install

dev: api

api:
	uv run uvicorn indie_market_analyst.api_server:app --reload

frontend:
	cd frontend && npm run dev

test:
	uv run pytest

seed-runs:
	uv run python -m indie_market_analyst.scripts.seed_runs

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

build:
	cd frontend && npm run build

docker-build:
	docker build -t indie-market-analyst:dev .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env indie-market-analyst:dev

clean:
	rm -rf frontend/dist frontend/node_modules
	rm -rf .ruff_cache .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
