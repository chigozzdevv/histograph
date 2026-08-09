import json
from pathlib import Path

import pytest
import yaml
from demo.train import FEATURES
from jsonschema import Draft202012Validator

from histograph.integrations.github.manifest import parse_manifest
from histograph.integrations.github.service import _resolve_repository_path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / ".histograph/deployments/mobile-money-fraud.yaml"


def test_checked_in_histograph_contract_is_complete_and_examples_validate() -> None:
    manifest = parse_manifest(MANIFEST_PATH.read_text())
    interface = manifest.spec.interface
    assert interface is not None
    input_path = ROOT / _resolve_repository_path(
        ".histograph/deployments/mobile-money-fraud.yaml", interface.input_schema.path
    )
    output_path = ROOT / _resolve_repository_path(
        ".histograph/deployments/mobile-money-fraud.yaml", interface.output_schema.path
    )
    examples_path = ROOT / _resolve_repository_path(
        ".histograph/deployments/mobile-money-fraud.yaml", interface.examples.path
    )
    input_schema = json.loads(input_path.read_text())
    output_schema = json.loads(output_path.read_text())
    examples = yaml.safe_load(examples_path.read_text())["examples"]

    assert set(input_schema["required"]) == set(FEATURES)
    assert output_schema["properties"]["score"]["maximum"] == 1
    validator = Draft202012Validator(input_schema)
    for example in examples:
        validator.validate(example["input"])


def test_manifest_resource_resolution_cannot_escape_the_repository() -> None:
    with pytest.raises(ValueError, match="inside the repository"):
        _resolve_repository_path(".histograph/deployments/fraud.yaml", "../../../secret")
