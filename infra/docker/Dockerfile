# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core packages/core
COPY packages/sdk-python packages/sdk-python
COPY apps/api apps/api
COPY apps/cli apps/cli
RUN uv sync --frozen --no-dev --package growth-model-api --extra postgres
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["growth-model-server", "serve", "--host", "0.0.0.0", "--port", "8000"]
