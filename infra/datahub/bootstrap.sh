#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

"$SCRIPT_DIR/start.sh"
"$SCRIPT_DIR/health.sh"

gms_url="${DATAHUB_GMS_URL:-${HISTOGRAPH_DATAHUB_GMS_URL:-http://localhost:8080}}"
token="${DATAHUB_GMS_TOKEN:-${HISTOGRAPH_DATAHUB_GMS_TOKEN:-}}"

if [[ -z "$token" ]]; then
    datahub_cli init \
        --host "$gms_url" \
        --username "${DATAHUB_USERNAME:-datahub}" \
        --password "${DATAHUB_PASSWORD:-datahub}" \
        --token-duration "${DATAHUB_TOKEN_DURATION:-no_expiry}" \
        --force

    datahub_config_file="${HOME}/.datahubenv"
    if [[ ! -f "$datahub_config_file" ]]; then
        printf 'DataHub CLI did not create %s\n' "$datahub_config_file" >&2
        exit 1
    fi
    token="$(awk '$1 == "token:" {print $2; exit}' "$datahub_config_file")"
fi

if [[ -z "$token" || "$token" == "null" ]]; then
    printf 'A DataHub access token is required to configure Histograph MCP.\n' >&2
    exit 1
fi

umask 077
mkdir -p "$(dirname -- "$DATAHUB_ENV_FILE")"
{
    printf 'DATAHUB_GMS_URL=%s\n' "$gms_url"
    printf 'DATAHUB_GMS_TOKEN=%s\n' "$token"
    printf 'HISTOGRAPH_DATAHUB_GMS_URL=%s\n' "$gms_url"
    printf 'HISTOGRAPH_DATAHUB_GMS_TOKEN=%s\n' "$token"
    printf 'HISTOGRAPH_DATAHUB_MCP_COMMAND=uvx\n'
    printf 'HISTOGRAPH_DATAHUB_MCP_PACKAGE=mcp-server-datahub==0.6.0\n'
    printf 'HISTOGRAPH_DATAHUB_MCP_PYTHON=3.13\n'
    printf 'HISTOGRAPH_DATAHUB_MCP_MUTATIONS_ENABLED=false\n'
} >"$DATAHUB_ENV_FILE"
chmod 600 "$DATAHUB_ENV_FILE"

"$SCRIPT_DIR/mcp-health.sh"

printf 'DataHub is ready.\n'
printf 'Environment written to %s\n' "$DATAHUB_ENV_FILE"
printf 'Load it with: set -a; source %s; set +a\n' "$DATAHUB_ENV_FILE"
