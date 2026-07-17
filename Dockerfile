# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.9.15 AS uv

FROM python:3.12.12-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=never

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STORYFORGE_API_HOST=0.0.0.0 \
    STORYFORGE_API_PORT=8000

RUN groupadd --gid 10001 storyforge && \
    useradd --uid 10001 --gid storyforge --create-home --home-dir /home/storyforge storyforge && \
    mkdir -p /app /tmp/storyforge && \
    chown -R storyforge:storyforge /app /tmp/storyforge /home/storyforge

WORKDIR /app
COPY --from=builder --chown=storyforge:storyforge /app/.venv /app/.venv
COPY --chown=storyforge:storyforge alembic.ini ./alembic.ini
COPY --chown=storyforge:storyforge alembic ./alembic

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
    CMD ["storyforge-healthcheck"]

CMD ["storyforge-api"]
