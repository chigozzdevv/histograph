#!/usr/bin/env bash
set -euo pipefail

uv run --extra demo ruff check server/src server/tests demo
uv run --extra demo ruff format --check server/src server/tests demo
uv run --extra demo pyrefly check
uv run --extra demo pytest
