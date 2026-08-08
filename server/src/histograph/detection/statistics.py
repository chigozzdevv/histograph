from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from math import log


@dataclass(frozen=True)
class BinaryMetrics:
    count: int
    positive_predictions: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    accuracy: float | None


def calculate_binary_metrics(
    predictions: Iterable[tuple[bool, bool]],
) -> BinaryMetrics:
    true_positives = false_positives = false_negatives = true_negatives = 0
    for predicted, actual in predictions:
        if predicted and actual:
            true_positives += 1
        elif predicted and not actual:
            false_positives += 1
        elif not predicted and actual:
            false_negatives += 1
        else:
            true_negatives += 1

    count = true_positives + false_positives + false_negatives + true_negatives
    positive_predictions = true_positives + false_positives
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    false_positive_denominator = false_positives + true_negatives
    false_negative_denominator = false_negatives + true_positives
    precision = true_positives / precision_denominator if precision_denominator else None
    recall = true_positives / recall_denominator if recall_denominator else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )

    return BinaryMetrics(
        count=count,
        positive_predictions=positive_predictions,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        true_negatives=true_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=(
            false_positives / false_positive_denominator
            if false_positive_denominator
            else None
        ),
        false_negative_rate=(
            false_negatives / false_negative_denominator
            if false_negative_denominator
            else None
        ),
        accuracy=((true_positives + true_negatives) / count if count else None),
    )


def population_stability_index(
    baseline: Iterable[float], current: Iterable[float], bins: int = 10
) -> float:
    baseline_values = list(baseline)
    current_values = list(current)
    if not baseline_values or not current_values:
        return 0.0
    if bins < 2:
        raise ValueError("bins must be at least 2")

    ordered_baseline = sorted(baseline_values)
    if ordered_baseline[0] == ordered_baseline[-1] and all(
        value == ordered_baseline[0] for value in current_values
    ):
        return 0.0

    boundaries = sorted(
        {
            ordered_baseline[min(len(ordered_baseline) - 1, index * len(ordered_baseline) // bins)]
            for index in range(1, bins)
        }
    )
    bucket_count = len(boundaries) + 1
    baseline_counts = [0] * bucket_count
    current_counts = [0] * bucket_count

    for value in baseline_values:
        baseline_counts[bisect_right(boundaries, value)] += 1
    for value in current_values:
        current_counts[bisect_right(boundaries, value)] += 1

    baseline_size = len(baseline_values)
    current_size = len(current_values)
    epsilon = 1e-6
    score = 0.0
    for baseline_count, current_count in zip(baseline_counts, current_counts, strict=True):
        baseline_ratio = max(baseline_count / baseline_size, epsilon)
        current_ratio = max(current_count / current_size, epsilon)
        score += (current_ratio - baseline_ratio) * log(current_ratio / baseline_ratio)
    return score
