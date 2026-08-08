#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

args=(
    docker
    quickstart
    --version "$DATAHUB_QUICKSTART_VERSION"
    --dump-logs-on-failure
)

if [[ "${DATAHUB_PULL_IMAGES:-true}" == "true" ]]; then
    args+=(--pull-images)
else
    args+=(--no-pull-images)
fi

if [[ -n "${DATAHUB_MYSQL_PORT:-}" ]]; then
    args+=(--mysql-port "$DATAHUB_MYSQL_PORT")
fi

if [[ -n "${DATAHUB_KAFKA_BROKER_PORT:-}" ]]; then
    args+=(--kafka-broker-port "$DATAHUB_KAFKA_BROKER_PORT")
fi

if [[ -n "${DATAHUB_ELASTIC_PORT:-}" ]]; then
    args+=(--elastic-port "$DATAHUB_ELASTIC_PORT")
fi

datahub_cli "${args[@]}"
