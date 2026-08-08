#!/usr/bin/env bash
set -euo pipefail

uv sync --dev
./scripts/compose.sh up -d postgres clickhouse redis
./infra/datahub/bootstrap.sh
