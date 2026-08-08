import pytest

from histograph.integrations.datahub.client import DataHubMcpError, _require_entity


def test_require_entity_accepts_expected_urn() -> None:
    _require_entity([{"urn": "urn:li:mlModel:fraud"}], "urn:li:mlModel:fraud")


def test_require_entity_surfaces_datahub_lookup_error() -> None:
    with pytest.raises(DataHubMcpError, match="Entity not found"):
        _require_entity(
            [{"urn": "urn:li:mlModel:fraud", "error": "Entity not found"}],
            "urn:li:mlModel:fraud",
        )
