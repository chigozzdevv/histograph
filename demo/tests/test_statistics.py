import numpy as np
import pytest
from demo.statistics import comparison, population_stability_index


def test_comparison_reports_relative_performance_degradation() -> None:
    result = comparison(0.80, 0.60)

    assert result["absolute_change_percentage_points"] == pytest.approx(-20.0)
    assert result["relative_change_percent"] == pytest.approx(-25.0)
    assert result["degradation_percent"] == pytest.approx(25.0)
    assert result["direction"] == "degraded"


def test_psi_detects_constant_value_distribution_shift() -> None:
    baseline = np.full(100, 1.0)
    current = np.full(100, 10.0)

    assert population_stability_index(baseline, current) > 20


def test_psi_is_zero_when_both_constant_distributions_match() -> None:
    values = np.full(100, 3.0)

    assert population_stability_index(values, values) == 0.0
