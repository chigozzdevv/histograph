#!/usr/bin/env bash
set -euo pipefail

uv run ruff check server/src server/tests
uv run ruff format --check server/src server/tests
uv run pyrefly check
uv run pytest
