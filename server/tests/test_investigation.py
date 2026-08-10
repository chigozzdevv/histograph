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

    def get(self, incident_id) -> dict[str, Any] | None:
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


class FakeRecoveredControl(FakeControl):
    def get(self, incident_id):
        incident = super().get(incident_id)
        if incident is None:
            return None
        incident["evidence"]["recovery"] = {
            "status": "verified",
            "verified_at": "2026-08-08T12:30:00+00:00",
            "checks": [
                {
                    "name": "fresh_performance_window_passed",
                    "passed": True,
                    "details": {"recall": 0.82},
                }
            ],
        }
        return incident


class FakeRecoveredReleaseHistory:
    def collect(self, incident, asset_urns):
        feature_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)"
        assert feature_urn in asset_urns
        common = {
            "asset_urn": feature_urn,
            "asset_name": "account-velocity-job",
            "asset_type": "data_job",
            "metadata": {"changed_features": ["merchant_velocity"]},
            "lineage_match": True,
        }
        return {
            "changes": [
                {
                    **common,
                    "version": "v2",
                    "change_type": "configuration",
                    "status": "applied",
                    "occurred_at": "2026-08-08T11:00:00+00:00",
                },
                {
                    **common,
                    "version": "v1",
                    "change_type": "rollback",
                    "status": "rolled_back",
                    "occurred_at": "2026-08-08T12:00:00+00:00",
                },
            ],
            "deployments": [],
        }


@pytest.mark.asyncio
async def test_final_writeback_includes_verified_recovery_evidence():
    control = FakeRecoveredControl()
    datahub = FakeDataHub()
    agent = InvestigationAgent(control, datahub, FakeRecoveredReleaseHistory())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
        write_back=True,
    )

    assert result["status"] == "confirmed_cause"
    assert datahub.saved is not None
    content = datahub.saved[1]
    assert "## Recovery evidence" in content
    assert "2026-08-08T12:30:00+00:00" in content
    assert "fresh_performance_window_passed" in content
    assert '"recall": 0.82' in content


class FakeRecoveredCanaryControl(FakeRecoveredControl):
    def get(self, incident_id):
        incident = super().get(incident_id)
        if incident is None:
            return None
        incident["signal"] = "performance"
        incident["metric"] = "recall"
        incident["evidence"]["detection"] = {
            "comparison_type": "candidate_against_reference_version"
        }
        return incident


class FakeStoppedCanaryHistory:
    def collect(self, incident, asset_urns):
        return {
            "changes": [],
            "deployments": [
                {
                    "deployment": "fraud-production",
                    "version": "v2",
                    "strategy": "canary",
                    "status": "stopped",
                    "traffic_percentage": 0,
                    "occurred_at": "2026-08-08T12:00:00+00:00",
                },
                {
                    "deployment": "fraud-production",
                    "version": "v2",
                    "strategy": "canary",
                    "status": "active",
                    "traffic_percentage": 10,
                    "occurred_at": "2026-08-08T11:00:00+00:00",
                },
            ],
        }


@pytest.mark.asyncio
async def test_verified_zero_traffic_canary_stop_confirms_the_model_release():
    control = FakeRecoveredCanaryControl()
    agent = InvestigationAgent(control, FakeNoLineageDataHub(), FakeStoppedCanaryHistory())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert result["status"] == "confirmed_cause"
    assert result["root_cause"]["kind"] == "model_release"
    assert result["root_cause"]["rollback_observed"] is True


class FakeReleaseHistory:
    def collect(self, incident, asset_urns):
        feature_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)"
        assert feature_urn in asset_urns
        return {
            "window": {
                "start": "2026-08-08T10:30:00+00:00",
                "end": "2026-08-08T12:00:00+00:00",
            },
            "changes": [
                {
                    "asset_urn": feature_urn,
                    "asset_name": "account-velocity-job",
                    "asset_type": "data_job",
                    "version": "v2",
                    "change_type": "configuration",
                    "status": "applied",
                    "occurred_at": "2026-08-08T11:00:00+00:00",
                    "metadata": {"changed_features": ["merchant_velocity"]},
                    "lineage_match": True,
                }
            ],
            "deployments": [],
        }


class ActiveCanaryHistory:
    def collect(self, incident, asset_urns):
        return {
            "changes": [],
            "deployments": [
                {
                    "deployment": "fraud-production",
                    "version": "v2",
                    "strategy": "canary",
                    "status": "active",
                    "traffic_percentage": 10,
                    "occurred_at": "2026-08-08T08:00:00+00:00",
                    "evidence_basis": "active_deployment_state",
                }
            ],
        }


class RestartedCanaryHistory:
    def collect(self, incident, asset_urns):
        return {
            "changes": [],
            "deployments": [
                {
                    "deployment": "fraud-production",
                    "version": "v2",
                    "strategy": "canary",
                    "status": "active",
                    "traffic_percentage": 10,
                    "occurred_at": "2026-08-08T12:00:00+00:00",
                },
                {
                    "deployment": "fraud-production",
                    "version": "v2",
                    "strategy": "canary",
                    "status": "stopped",
                    "traffic_percentage": 0,
                    "occurred_at": "2026-08-08T11:00:00+00:00",
                },
            ],
        }


class FakeActiveCanaryControl(FakeControl):
    def get(self, incident_id):
        incident = super().get(incident_id)
        if incident is None:
            return None
        incident["signal"] = "performance"
        incident["metric"] = "recall"
        incident["evidence"]["detection"] = {
            "comparison_type": "candidate_against_reference_version"
        }
        return incident


@pytest.mark.asyncio
async def test_active_canary_state_supports_probable_cause_outside_release_window():
    control = FakeActiveCanaryControl()
    agent = InvestigationAgent(control, FakeNoLineageDataHub(), ActiveCanaryHistory())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert result["status"] == "probable_cause"
    assert result["root_cause"]["kind"] == "model_release"
    assert result["root_cause"]["evidence_basis"] == "active_deployment_state"
    assert "runtime-confirmed canary candidate was actively serving" in result["summary"]


@pytest.mark.asyncio
async def test_restarted_canary_does_not_inherit_an_older_rollback_state():
    control = FakeActiveCanaryControl()
    agent = InvestigationAgent(control, FakeNoLineageDataHub(), RestartedCanaryHistory())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert result["status"] == "probable_cause"
    assert result["root_cause"]["status"] == "active"
    assert result["root_cause"]["traffic_percentage"] == 10
    assert result["root_cause"]["rollback_observed"] is False


@pytest.mark.asyncio
async def test_investigation_identifies_a_lineage_matched_feature_release_as_probable():
    control = FakeControl()
    agent = InvestigationAgent(control, FakeDataHub(), FakeReleaseHistory())

    result = await agent.investigate(
        control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert result["status"] == "probable_cause"
    assert result["root_cause"]["kind"] == "upstream_release"
    assert result["root_cause"]["asset_name"] == "account-velocity-job"
    assert result["hypotheses"][0]["status"] == "supported"
    assert control.updated is not None
    assert control.updated[2]["root_cause_status"] == "probable_cause"


class FakeNoLineageDataHub(FakeDataHub):
    async def collect_context(self, model_urn, max_hops):
        return {
            "model": {"urn": model_urn, "type": "ML_MODEL", "name": "fraud-v2"},
            "upstream": {"upstreams": {"searchResults": []}},
            "downstream": {"downstreams": {"searchResults": []}},
            "related_entities": [],
            "tool_trace": ["get_entities"],
        }


class AblationReleaseHistory:
    def collect(self, incident, asset_urns):
        feature_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)"
        return {
            "changes": [
                {
                    "asset_urn": feature_urn,
                    "asset_name": "account-velocity-job",
                    "version": "v2",
                    "change_type": "configuration",
                    "status": "applied",
                    "metadata": {"changed_features": ["merchant_velocity"]},
                    "lineage_match": feature_urn in asset_urns,
                }
            ],
            "deployments": [],
        }


@pytest.mark.asyncio
async def test_datahub_enabled_vs_disabled_ablation_changes_the_operational_decision():
    enabled_control = FakeControl()
    disabled_control = FakeControl()
    enabled = InvestigationAgent(
        enabled_control,
        FakeDataHub(),
        AblationReleaseHistory(),
    )
    disabled = InvestigationAgent(
        disabled_control,
        FakeNoLineageDataHub(),
        AblationReleaseHistory(),
    )

    enabled_result = await enabled.investigate(
        enabled_control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )
    disabled_result = await disabled.investigate(
        disabled_control.incident_id,
        "urn:li:mlModel:fraud-v2",
        max_hops=2,
    )

    assert enabled_result["status"] == "probable_cause"
    assert "request approval to roll back" in enabled_result["recommended_action"]
    assert disabled_result["status"] == "insufficient_evidence"
    assert "only approve rollback" in disabled_result["recommended_action"]


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
