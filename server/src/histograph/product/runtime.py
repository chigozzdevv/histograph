from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator


class RuntimeConnector:
    def __init__(
        self,
        allowed_hosts: list[str],
        control_token: str | None,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._allowed_hosts = {host.lower() for host in allowed_hosts}
        self._control_token = control_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def predict(
        self,
        deployment: dict[str, Any],
        features: dict[str, Any],
    ) -> dict[str, Any]:
        self.validate_input(deployment, features)
        endpoint = self._endpoint(deployment)
        return await self._post(
            endpoint,
            "/v1/predict",
            {"prediction_id": f"playground-{uuid4().hex}", "features": features},
        )

    async def compare(
        self,
        deployment: dict[str, Any],
        features: dict[str, Any],
    ) -> dict[str, Any]:
        self.validate_input(deployment, features)
        if self._control_token is None:
            raise RuntimeError("Reference runtime control token is not configured")
        endpoint = self._endpoint(deployment)
        return await self._post(
            endpoint,
            "/v1/compare",
            {"prediction_id": f"comparison-{uuid4().hex}", "features": features},
            token=self._control_token,
        )

    @staticmethod
    def validate_input(deployment: dict[str, Any], features: dict[str, Any]) -> None:
        schema = deployment.get("input_schema")
        if not isinstance(schema, dict):
            raise ValueError("Deployment has no resolved input schema")
        errors = sorted(
            Draft202012Validator(schema).iter_errors(features),
            key=lambda error: list(error.path),
        )
        if errors:
            messages = []
            for error in errors[:10]:
                path = ".".join(str(item) for item in error.path) or "$"
                messages.append(f"{path}: {error.message}")
            raise ValueError("Input does not match the deployment schema: " + "; ".join(messages))

    def _endpoint(self, deployment: dict[str, Any]) -> str:
        manifest = deployment.get("manifest")
        runtime = manifest.get("spec", {}).get("runtime") if isinstance(manifest, dict) else None
        endpoint = runtime.get("endpoint") if isinstance(runtime, dict) else None
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("Deployment runtime endpoint is not configured")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Deployment runtime endpoint must be an HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Deployment runtime endpoint cannot contain credentials or URL state")
        if parsed.hostname.lower() not in self._allowed_hosts:
            raise PermissionError("Deployment runtime host is not in the configured allowlist")
        return endpoint.rstrip("/")

    async def _post(
        self,
        endpoint: str,
        path: str,
        payload: dict[str, Any],
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else None
        async with httpx.AsyncClient(
            base_url=endpoint,
            timeout=self._timeout_seconds,
            transport=self._transport,
            headers=headers,
        ) as client:
            response = await client.post(path, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Reference runtime returned a non-object response")
        return body
