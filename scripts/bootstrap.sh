#!/usr/bin/env bash
set -euo pipefail

uv sync --dev
docker compose up -d postgres clickhouse redis
./infra/datahub/bootstrap.sh
