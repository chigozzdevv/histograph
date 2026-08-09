from bisect import bisect_right
from math import log
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def classification_metrics(
    actual: np.ndarray, scores: np.ndarray, threshold: float
) -> dict[str, float | int]:
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(actual, predicted, labels=[0, 1]).ravel()
    negative_count = tn + fp
    unique_actual = np.unique(actual)
    return {
        "count": int(len(actual)),
        "positive_count": int(np.sum(actual)),
        "positive_prevalence": float(np.mean(actual)),
        "threshold": float(threshold),
        "average_precision": float(average_precision_score(actual, scores)),
        "roc_auc": (
            float(roc_auc_score(actual, scores)) if len(unique_actual) == 2 else float("nan")
        ),
        "accuracy": float(accuracy_score(actual, predicted)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "false_positive_rate": float(fp / negative_count if negative_count else 0.0),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_negatives": int(tn),
    }


def select_threshold(
    actual: np.ndarray, scores: np.ndarray, max_false_positive_rate: float = 0.05
) -> float:
    candidates = np.unique(np.quantile(scores, np.linspace(0.01, 0.99, 199)))
    viable: list[tuple[float, float, float]] = []
    fallback: list[tuple[float, float]] = []
    actual_positive = np.asarray(actual) == 1
    actual_negative = ~actual_positive
    for threshold in candidates:
        predicted_positive = scores >= threshold
        true_positives = int(np.sum(predicted_positive & actual_positive))
        false_positives = int(np.sum(predicted_positive & actual_negative))
        false_negatives = int(np.sum(~predicted_positive & actual_positive))
        true_negatives = int(np.sum(~predicted_positive & actual_negative))
        precision_denominator = true_positives + false_positives
        recall_denominator = true_positives + false_negatives
        precision = true_positives / precision_denominator if precision_denominator else 0.0
        recall = true_positives / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        negative_count = true_negatives + false_positives
        false_positive_rate = false_positives / negative_count if negative_count else 0.0
        fallback.append((f1, float(threshold)))
        if false_positive_rate <= max_false_positive_rate:
            viable.append((recall, precision, float(threshold)))
    if viable:
        return max(viable)[2]
    return max(fallback)[1]


def comparison(baseline: float, observed: float, lower_is_better: bool = False) -> dict[str, Any]:
    absolute = observed - baseline
    relative = absolute / abs(baseline) * 100 if baseline else None
    degraded = absolute > 0 if lower_is_better else absolute < 0
    degradation = None
    if relative is not None:
        degradation = relative if lower_is_better else -relative
    return {
        "baseline": baseline,
        "observed": observed,
        "absolute_change": absolute,
        "absolute_change_percentage_points": absolute * 100,
        "relative_change_percent": relative,
        "degradation_percent": degradation if degraded else 0.0,
        "direction": "degraded" if degraded else "improved" if absolute else "unchanged",
    }


def population_stability_index(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    baseline_values = np.asarray(baseline, dtype=float).tolist()
    current_values = np.asarray(current, dtype=float).tolist()
    if not baseline_values or not current_values:
        raise ValueError("PSI requires non-empty samples")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    ordered_baseline = sorted(baseline_values)
    if ordered_baseline[0] == ordered_baseline[-1]:
        reference = ordered_baseline[0]
        matching_current = sum(value == reference for value in current_values)
        if matching_current == len(current_values):
            return 0.0
        return _psi_from_counts(
            [len(baseline_values), 0],
            [matching_current, len(current_values) - matching_current],
        )
    boundaries = sorted(
        {
            ordered_baseline[min(len(ordered_baseline) - 1, index * len(ordered_baseline) // bins)]
            for index in range(1, bins)
        }
    )
    baseline_counts = [0] * (len(boundaries) + 1)
    current_counts = [0] * (len(boundaries) + 1)
    for value in baseline_values:
        baseline_counts[bisect_right(boundaries, value)] += 1
    for value in current_values:
        current_counts[bisect_right(boundaries, value)] += 1
    return _psi_from_counts(baseline_counts, current_counts)


def _psi_from_counts(baseline_counts: list[int], current_counts: list[int]) -> float:
    baseline_size = sum(baseline_counts)
    current_size = sum(current_counts)
    epsilon = 1e-6
    score = 0.0
    for baseline_count, current_count in zip(baseline_counts, current_counts, strict=True):
        baseline_ratio = max(baseline_count / baseline_size, epsilon)
        current_ratio = max(current_count / current_size, epsilon)
        score += (current_ratio - baseline_ratio) * log(current_ratio / baseline_ratio)
    return score
