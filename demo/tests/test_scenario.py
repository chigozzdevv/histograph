import pytest
from demo.scenario import (
    _most_degraded_metric,
    run_feature_release_scenario,
    run_model_canary_scenario,
)


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
