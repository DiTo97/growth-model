# https://just.systems — `just` lists recipes.
default:
    @just --list

# Install everything
setup:
    uv sync
    cd packages/sdk-js && npm ci

# Everything CI runs
check: lint typecheck test

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

typecheck:
    uv run pyright
    cd packages/sdk-js && npm run typecheck

test:
    uv run pytest
    cd packages/sdk-js && npm test

# Run the API locally on :8000
serve:
    uv run growth-model-server serve --port 8000

# Serve the web console on :5173
web:
    cd apps/web && python3 -m http.server 5173

# Try the model on synthetic data
demo:
    uv run growth-model demo-data /tmp/growth-demo.csv
    uv run growth-model levers /tmp/growth-demo.csv --table
