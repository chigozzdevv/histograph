#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/common.sh"
load_datahub_env

if [[ -z "${HISTOGRAPH_DATAHUB_GMS_TOKEN:-${DATAHUB_GMS_TOKEN:-}}" ]]; then
    printf 'A DataHub token is required for the MCP health check. Run bootstrap.sh first.\n' >&2
    exit 1
fi

PYTHONPATH="$REPO_ROOT/server/src${PYTHONPATH:+:$PYTHONPATH}" uv run python - <<'PY'
import asyncio

from histograph.integrations.datahub.client import DataHubMcpClient
from histograph.settings import Settings


async def main() -> None:
    health = await DataHubMcpClient(Settings()).health_check()
    tools = health.get("tools")
    if not isinstance(tools, list) or not tools:
        raise RuntimeError("DataHub MCP returned no tools")
    print(f"DataHub MCP healthy: {', '.join(str(tool) for tool in tools)}")


asyncio.run(main())
PY
