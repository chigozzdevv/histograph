from pathlib import Path

import pandas as pd
import pytest
import yaml
from demo import scenario
from demo.scenario import (
    _most_degraded_metric,
    emit_runtime_canary_traffic,
    run_feature_release_scenario,
    run_model_canary_scenario,
)
from demo.train import FEATURES


def test_scenario_selects_the_largest_directional_degradation() -> None:
    metric, operator, degradation = _most_degraded_metric(
        {"recall": 0.8, "f1": 0.7, "false_positive_rate": 0.02},
        {"recall": 0.7, "f1": 0.4, "false_positive_rate": 0.12},
    )

    assert metric == "false_positive_rate"
    assert operator == "increase"
    assert degradation == pytest.approx(500.0)


@pytest.mark.parametrize(
    "runner",
    [run_feature_release_scenario, run_model_canary_scenario],
)
def test_write_back_requires_investigations(runner, tmp_path) -> None:
    with pytest.raises(ValueError, match="write-back requires investigations"):
        runner(
            "http://localhost:8000",
            tmp_path / "prepared.parquet",
            tmp_path / "model.joblib",
            investigate=False,
            write_back=True,
        )


def test_runtime_replay_reports_delivered_outcome_count(monkeypatch) -> None:
    manifest = yaml.safe_load((Path(__file__).parents[1] / "deployment.yaml").read_text())
    frame = pd.DataFrame(
        [
            {
                **{feature: 0 for feature in FEATURES if feature != "transaction_type"},
                "transaction_type": "TRANSFER",
                "is_fraud": index % 2,
            }
            for index in range(4)
        ]
    )
    runtime_outcomes: list[dict] = []

    class FakeApi:
        def __init__(self, base_url: str):
            self.base_url = base_url

        def get(self, path: str):
            assert (self.base_url, path) == ("http://runtime", "/v1/runtime")
            return {"status": "ready", "revision": "canary-sha", "manifest": manifest}

        def post(self, path: str, payload: dict):
            if self.base_url == "http://runtime" and path == "/v1/predict/batch":
                return {
                    "events": [
                        {**event, "version": "v1" if index < 2 else "v2"}
                        for index, event in enumerate(payload["events"])
                    ]
                }
            if self.base_url == "http://runtime" and path == "/v1/outcomes/batch":
                runtime_outcomes.extend(payload["events"])
                return {"accepted": len(payload["events"])}
            if self.base_url == "http://api" and path == "/v1/monitors":
                return {"id": "65a978e6-06eb-4475-9b61-4097c37451ae"}
            raise AssertionError(f"Unexpected request: {self.base_url}{path}")

        def close(self):
            return None

    monkeypatch.setattr(scenario, "HistographApi", FakeApi)
    monkeypatch.setattr(
        scenario,
        "_load_artifact",
        lambda _path: {"manifest": {"split": {"test": {"start": 0}}}},
    )
    monkeypatch.setattr(scenario, "_load_replay_frame", lambda *_args: frame)
    monkeypatch.setattr(scenario, "_wait_for_outbox", lambda *_args: None)

    result = emit_runtime_canary_traffic(
        "http://api",
        "http://runtime",
        Path("prepared.parquet"),
        Path("artifact.joblib"),
        sample_size=4,
    )

    assert result["routing_counts"] == {"v1": 2, "v2": 2}
    assert result["outcome_count"] == 4
    assert len(runtime_outcomes) == 4
