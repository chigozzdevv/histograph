from histograph.detection.statistics import calculate_binary_metrics, population_stability_index


def test_binary_metrics_are_calculated_from_prediction_outcome_pairs() -> None:
    metrics = calculate_binary_metrics(
        [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
    )

    assert metrics.count == 4
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.false_positive_rate == 0.5
    assert metrics.accuracy == 0.5


def test_population_stability_index_is_zero_for_identical_distributions() -> None:
    assert population_stability_index([1, 2, 3, 4], [1, 2, 3, 4]) == 0.0


def test_population_stability_index_increases_for_shifted_distribution() -> None:
    score = population_stability_index([1, 2, 3, 4], [8, 9, 10, 11])

    assert score > 0.0
