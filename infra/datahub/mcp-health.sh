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
    context = await DataHubMcpClient(Settings()).collect_context(
        "urn:li:mlModel:histograph-health-check", max_hops=1
    )
    trace = context.get("tool_trace")
    if not isinstance(trace, list) or not trace:
        raise RuntimeError("DataHub MCP returned no tool trace")
    print(f"DataHub MCP healthy: {', '.join(str(tool) for tool in trace)}")


asyncio.run(main())
PY
