.PHONY: setup lint typecheck test test-postgres migrate api demo docker-build docker-up docker-test clean docker-reset

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

docker-build:
	docker build -t storyforge:test .

docker-up:
	docker compose up --build -d

docker-test:
	docker compose exec api storyforge demo-m7 --output human

clean:
	uv run python scripts/clean.py

docker-reset:
	docker compose down -v
