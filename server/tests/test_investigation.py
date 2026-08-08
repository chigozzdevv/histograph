from typing import Any
from uuid import uuid4

import pytest

from histograph.agents.investigation.agent import InvestigationAgent


class FakeControl:
    def __init__(self):
        self.incident_id = uuid4()
        self.updated: tuple[Any, ...] | None = None

    def get_incident(self, incident_id):
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

    def update_incident(self, incident_id, summary, evidence):
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
                "searchResults": [
                    {
                        "degree": 1,
                        "entity": {
                            "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,features,PROD)",
                            "type": "DATASET",
                            "name": "features",
                        },
                    }
                ]
            },
            "downstream": {"searchResults": []},
            "related_entities": [],
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

    assert result["status"] == "lineage_mapped"
    assert result["lineage"]["upstream"][0]["name"] == "features"
    assert control.updated is not None
    assert control.updated[0] == control.incident_id
    assert control.updated[2]["root_cause_status"] == "lineage_mapped"


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
