#!/usr/bin/env bash
set -euo pipefail

if docker compose version >/dev/null 2>&1; then
    exec docker compose "$@"
fi

if command -v docker-compose >/dev/null 2>&1; then
    exec docker-compose "$@"
fi

printf 'Docker Compose is required. Install the Docker Compose plugin or docker-compose.\n' >&2
exit 1
