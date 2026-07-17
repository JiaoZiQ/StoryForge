.PHONY: setup lint typecheck test test-postgres migrate api demo frontend-install frontend-lint frontend-test frontend-build frontend-e2e docker-build docker-up docker-test clean docker-reset

setup:
	uv sync --locked --all-groups

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy src

test:
	uv run pytest

test-postgres:
	uv run pytest -m postgres --no-cov

migrate:
	uv run alembic upgrade head

api:
	uv run storyforge-api

demo:
	uv run storyforge demo-m6 --output human

frontend-install:
	cd frontend && npm ci

frontend-lint:
	cd frontend && npm run format:check && npm run lint && npm run typecheck

frontend-test:
	cd frontend && npm test

frontend-build:
	cd frontend && npm run build

frontend-e2e:
	cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npm run test:e2e

docker-build:
	docker build -t storyforge:test .
	docker build -f frontend/Dockerfile -t storyforge-web:test .
	docker build -f deploy/ingress.Dockerfile -t storyforge-gateway:test .

docker-up:
	docker compose up --build -d

docker-test:
	docker compose exec api storyforge demo-m9 --frontend-url http://localhost:3000 --output human

clean:
	uv run python scripts/clean.py

docker-reset:
	docker compose down -v
