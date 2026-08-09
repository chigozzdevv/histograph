from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from histograph.api.routes import product
from histograph.product.runtime import RuntimeConnector

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["amount", "transaction_type"],
    "properties": {
        "amount": {"type": "number", "minimum": 0},
        "transaction_type": {"type": "string", "enum": ["TRANSFER", "PAYMENT"]},
    },
}


def _deployment(endpoint: str = "http://runtime:8100") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "deployment": "fraud-production",
        "model": "fraud",
        "manifest": {"spec": {"runtime": {"endpoint": endpoint}}},
        "input_schema": SCHEMA,
        "manifest_content": "must-not-leak",
        "installation_id": 123,
    }


@pytest.mark.asyncio
async def test_runtime_connector_validates_inputs_and_keeps_compare_out_of_telemetry() -> None:
    calls: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/v1/predict":
            return httpx.Response(200, json={"version": "v1", "score": 0.1})
        if request.url.path == "/v1/compare":
            return httpx.Response(
                200,
                json={
                    "stable": {"version": "v1", "score": 0.1},
                    "candidate": {"version": "v2", "score": 0.1},
                },
            )
        raise AssertionError(f"Unexpected runtime request: {request.url}")

    connector = RuntimeConnector(
        ["runtime"],
        "runtime-control",
        5,
        transport=httpx.MockTransport(handler),
    )
    features = {"amount": 100.0, "transaction_type": "TRANSFER"}

    assert (await connector.predict(_deployment(), features))["version"] == "v1"
    comparison = await connector.compare(_deployment(), features)
    assert comparison["candidate"]["version"] == "v2"
    assert calls == [
        ("/v1/predict", None),
        ("/v1/compare", "Bearer runtime-control"),
    ]

    with pytest.raises(ValueError, match="required property"):
        await connector.predict(_deployment(), {"amount": 10})
    with pytest.raises(PermissionError, match="allowlist"):
        await connector.predict(_deployment("http://169.254.169.254"), features)


class FakeGitOps:
    def __init__(self) -> None:
        self.deployment = _deployment()

    def list_deployments(self) -> list[dict[str, Any]]:
        return [self.deployment]

    def get_deployment(self, deployment_id):
        return self.deployment if deployment_id == self.deployment["id"] else None

    def list_connections(self) -> list[dict[str, Any]]:
        return []


class FakeProduct:
    def overview(self) -> dict[str, Any]:
        return {"counts": {"deployments": 1}}

    def activity(self, limit: int) -> list[dict[str, Any]]:
        return [{"event_type": "deployment_observed", "limit": limit}]


class FakeRuntimeConnector:
    async def predict(self, deployment, features):
        return {"version": "v1", "features": features}

    async def compare(self, deployment, features):
        return {"stable": {"version": "v1"}, "candidate": {"version": "v2"}}


class FakeRateLimits:
    def __init__(self) -> None:
        self.allowed = True

    def consume(self, bucket, client_key, *, limit, window_seconds):
        assert (bucket, limit, window_seconds) == ("playground", 60, 60)
        return self.allowed


def test_product_routes_are_client_ready_and_do_not_expose_connection_secrets() -> None:
    app = FastAPI()
    app.state.gitops = FakeGitOps()
    app.state.product = FakeProduct()
    app.state.runtime_connector = FakeRuntimeConnector()
    app.state.settings = SimpleNamespace(playground_rate_limit_per_minute=60)
    app.state.rate_limits = FakeRateLimits()
    app.include_router(product.router)
    deployment_id = app.state.gitops.deployment["id"]

    with TestClient(app) as client:
        assert client.get("/v1/overview").json()["counts"]["deployments"] == 1
        listed = client.get("/v1/deployments").json()[0]
        assert "manifest_content" not in listed
        assert "installation_id" not in listed
        predicted = client.post(
            f"/v1/deployments/{deployment_id}/predict",
            json={"input": {"amount": 10, "transaction_type": "PAYMENT"}},
        )
        assert predicted.status_code == 200
        compared = client.post(
            f"/v1/deployments/{deployment_id}/compare",
            json={"input": {"amount": 10, "transaction_type": "PAYMENT"}},
        )
        assert compared.json()["telemetry_recorded"] is False
        assert client.get("/v1/activity?limit=7").json()[0]["limit"] == 7
        app.state.rate_limits.allowed = False
        limited = client.post(
            f"/v1/deployments/{deployment_id}/predict",
            json={"input": {"amount": 10, "transaction_type": "PAYMENT"}},
        )
        assert limited.status_code == 429
