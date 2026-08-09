from typing import Any, Protocol

import httpx

from histograph.remediation.types import ExecutionResult


class RemediationAdapter(Protocol):
    async def execute(self, action: dict[str, Any]) -> ExecutionResult: ...


class WebhookRemediationAdapter:
    def __init__(self, url: str, token: str | None = None, timeout_seconds: float = 30.0):
        self._url = url
        self._token = token
        self._timeout_seconds = timeout_seconds

    async def execute(self, action: dict[str, Any]) -> ExecutionResult:
        action_id = str(action["id"])
        headers = {"Idempotency-Key": action_id}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        payload = {
            "action_id": action_id,
            "action_type": action["action_type"],
            "target": action["target"],
            "evidence": action["evidence"],
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(self._url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Remediation webhook returned a non-object response")
        return ExecutionResult.model_validate(body)
