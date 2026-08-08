#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
load_datahub_env

gms_url="${HISTOGRAPH_DATAHUB_GMS_URL:-${DATAHUB_GMS_URL:-http://localhost:8080}}"
frontend_url="${DATAHUB_FRONTEND_URL:-http://localhost:9002}"
attempts="${DATAHUB_HEALTH_ATTEMPTS:-30}"
interval="${DATAHUB_HEALTH_INTERVAL_SECONDS:-2}"

wait_for_url() {
    local name="$1"
    local url="$2"
    local attempt

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
            printf '%s healthy: %s\n' "$name" "$url"
            return 0
        fi
        if ((attempt < attempts)); then
            sleep "$interval"
        fi
    done

    printf '%s is not healthy: %s\n' "$name" "$url" >&2
    return 1
}

wait_for_url "DataHub GMS" "${gms_url%/}/health"
wait_for_url "DataHub frontend" "${frontend_url%/}/"
