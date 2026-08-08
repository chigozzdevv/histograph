from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from histograph.agents.investigation.agent import InvestigationAgent
from histograph.api.routes import investigations
from histograph.settings import Settings


class FakeControl:
    def __init__(self):
        self.incident_id = uuid4()
        self.updated: tuple[Any, ...] | None = None

    def get(self, incident_id):
        if incident_id != self.incident_id:
            return None
        return {
            "id": incident_id,
            "model": "fraud",
            "version": "v2",
            "signal": "feature_drift",
            "metric": "merchant_velocity_psi",
            "evidence": {"detection": {"feature": "merchant_velocity", "psi": 0.42}},
        }

    def update(self, incident_id, summary, evidence):
        self.updated = (incident_id, summary, evidence)
        return True


class FakeDataHub:
    def __init__(self):
        self.saved: tuple[str, str, list[str]] | None = None

    async def collect_context(self, model_urn, max_hops):
        assert model_urn == "urn:li:mlModel:fraud-v2"
        assert max_hops == 2
        return {
            "model": {
                "urn": model_urn,
                "type": "ML_MODEL",
                "name": "fraud-v2",
            },
            "upstream": {
                "upstreams": {
                    "searchResults": [
                        {
                            "degree": 1,
                            "entity": {
                                "urn": (
                                    "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)"
                                ),
                                "type": "DATASET",
                                "name": "features",
                                "ownership": {
                                    "owners": [
                                        {
                                            "owner": {
                                                "urn": "urn:li:corpuser:risk-data",
                                                "properties": {"displayName": "Risk Data Platform"},
                                            }
                                        }
                                    ]
                                },
                            },
                        }
                    ]
                }
            },
            "downstream": {"downstreams": {"searchResults": []}},
            "related_entities": [
                {
                    "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)",
                    "type": "DATASET",
                    "name": "features",
                    "ownership": {
                        "owners": [
                            {
                                "owner": {
                                    "urn": "urn:li:corpuser:risk-data",
                                    "properties": {"displayName": "Risk Data Platform"},
                                }
                            }
                        ]
                    },
                }
            ],
            "tool_trace": ["get_entities", "get_lineage:upstream", "get_lineage:downstream"],
        }

    async def save_investigation(self, title, content, related_assets):
        self.saved = (title, content, related_assets)
        return {"urn": "urn:li:document:histograph-incident"}


@pytest.mark.asyncio
async def test_investigation_maps_lineage_and_updates_incident():
    control = FakeControl()
    agent = InvestigationAgent(control, FakeDataHub())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert result["status"] == "insufficient_evidence"
    assert result["lineage_status"] == "mapped"
    assert result["lineage"]["upstream"][0]["name"] == "features"
    assert result["owners"] == ["Risk Data Platform"]
    assert control.updated is not None
    assert control.updated[0] == control.incident_id
    assert control.updated[2]["root_cause_status"] == "insufficient_evidence"


@pytest.mark.asyncio
async def test_investigation_writeback_is_explicit():
    control = FakeControl()
    datahub = FakeDataHub()
    agent = InvestigationAgent(control, datahub)

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
        write_back=True,
    )

    assert result["writeback"]["urn"] == "urn:li:document:histograph-incident"
    assert datahub.saved is not None
    assert "Histograph investigation" in datahub.saved[0]


class FakeModels:
    def __init__(self, datahub_urn: str | None):
        self.datahub_urn = datahub_urn

    def get(self, model_name):
        if model_name != "fraud":
            return None
        return {"name": model_name, "datahub_urn": self.datahub_urn}


def _investigation_api(control: FakeControl, models: FakeModels) -> FastAPI:
    app = FastAPI()
    app.state.incidents = control
    app.state.models = models
    app.state.settings = Settings()
    app.include_router(investigations.router)
    return app


def test_investigation_api_uses_the_registered_datahub_urn(monkeypatch):
    control = FakeControl()
    calls: list[tuple[Any, ...]] = []

    class FakeApiAgent:
        def __init__(self, incident_control, datahub):
            assert incident_control is control

        async def investigate(self, incident_id, model_urn, max_hops, write_back):
            calls.append((incident_id, model_urn, max_hops, write_back))
            return {"incident_id": incident_id, "model_urn": model_urn}

    monkeypatch.setattr(investigations, "InvestigationAgent", FakeApiAgent)
    monkeypatch.setattr(investigations, "DataHubMcpClient", lambda settings: object())

    with TestClient(
        _investigation_api(control, FakeModels("urn:li:mlModel:registered-fraud"))
    ) as client:
        response = client.post(
            f"/v1/investigations/{control.incident_id}",
            json={"max_hops": 2, "write_back": False},
        )

    assert response.status_code == 200
    assert calls == [(control.incident_id, "urn:li:mlModel:registered-fraud", 2, False)]


def test_investigation_api_rejects_models_without_a_datahub_urn():
    control = FakeControl()

    with TestClient(_investigation_api(control, FakeModels(None))) as client:
        response = client.post(
            f"/v1/investigations/{control.incident_id}",
            json={"max_hops": 2},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Registered model has no DataHub URN"


def test_investigation_api_rejects_a_caller_supplied_model_urn():
    control = FakeControl()

    with TestClient(
        _investigation_api(control, FakeModels("urn:li:mlModel:registered-fraud"))
    ) as client:
        response = client.post(
            f"/v1/investigations/{control.incident_id}",
            json={"model_urn": "urn:li:mlModel:untrusted"},
        )

    assert response.status_code == 422
