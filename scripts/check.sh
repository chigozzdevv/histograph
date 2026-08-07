#!/usr/bin/env bash
set -euo pipefail

uv run ruff check server/src server/tests
uv run pytest
