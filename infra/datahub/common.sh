#!/usr/bin/env bash
set -euo pipefail

DATAHUB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATAHUB_CLI_VERSION="${DATAHUB_CLI_VERSION:-1.6.0}"
DATAHUB_QUICKSTART_VERSION="${DATAHUB_QUICKSTART_VERSION:-v1.6.0}"
DATAHUB_PYTHON="${DATAHUB_PYTHON:-3.13}"
DATAHUB_ENV_FILE="${DATAHUB_ENV_FILE:-${DATAHUB_DIR}/.env}"

datahub_cli() {
    uvx \
        --python "$DATAHUB_PYTHON" \
        --from "acryl-datahub==${DATAHUB_CLI_VERSION}" \
        datahub "$@"
}

load_datahub_env() {
    if [[ -f "$DATAHUB_ENV_FILE" ]]; then
        set -a
        source "$DATAHUB_ENV_FILE"
        set +a
    fi
}
