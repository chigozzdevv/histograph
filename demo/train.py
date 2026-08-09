import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from demo.statistics import (
    classification_metrics,
    comparison,
    population_stability_index,
    select_threshold,
)

NUMERIC_FEATURES = [
    "amount",
    "old_balance_initiator",
    "new_balance_initiator",
    "old_balance_recipient",
    "new_balance_recipient",
    "initiator_balance_delta",
    "recipient_balance_delta",
    "account_velocity_24h",
    "recipient_velocity_24h",
]
CATEGORICAL_FEATURES = ["transaction_type"]
FEATURES = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    boundaries: dict[str, float]


def train_reference_model(
    prepared_path: Path,
    artifact_path: Path,
    manifest_path: Path,
    max_rows: int = 400_000,
    random_state: int = 42,
) -> dict[str, Any]:
    frame = _load_sample(prepared_path, max_rows)
    splits = _temporal_split(frame)
    candidates: dict[str, Pipeline] = {
        "logistic_regression": _logistic_pipeline(random_state),
        "hist_gradient_boosting": _boosting_pipeline(random_state),
    }
    validation_results: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Pipeline] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(splits.train[FEATURES], splits.train["is_fraud"])
        scores = pipeline.predict_proba(splits.validation[FEATURES])[:, 1]
        threshold = select_threshold(splits.validation["is_fraud"].to_numpy(), scores)
        validation_results[name] = classification_metrics(
            splits.validation["is_fraud"].to_numpy(), scores, threshold
        )
        fitted[name] = pipeline

    selected_name = max(
        validation_results,
        key=lambda name: float(validation_results[name]["average_precision"]),
    )
    selected = fitted[selected_name]
    threshold = float(validation_results[selected_name]["threshold"])
    test_actual = splits.test["is_fraud"].to_numpy()
    healthy_scores = selected.predict_proba(splits.test[FEATURES])[:, 1]
    healthy_metrics = classification_metrics(test_actual, healthy_scores, threshold)

    shifted = splits.test[FEATURES].copy()
    shifted["amount"] = shifted["amount"] * 100
    shifted_scores = selected.predict_proba(shifted)[:, 1]
    shifted_metrics = classification_metrics(test_actual, shifted_scores, threshold)

    ablated_features = [feature for feature in FEATURES if feature != "amount"]
    ablated = _pipeline(selected_name, random_state, ablated_features)
    ablated.fit(splits.train[ablated_features], splits.train["is_fraud"])
    ablated_scores = ablated.predict_proba(splits.validation[ablated_features])[:, 1]
    ablated_ap = float(
        classification_metrics(
            splits.validation["is_fraud"].to_numpy(),
            ablated_scores,
            select_threshold(splits.validation["is_fraud"].to_numpy(), ablated_scores),
        )["average_precision"]
    )

    assessment = {
        "changed_feature_psi": population_stability_index(
            splits.test["amount"].to_numpy(),
            shifted["amount"].to_numpy(),
        ),
        "score_psi": population_stability_index(healthy_scores, shifted_scores),
        "recall": comparison(float(healthy_metrics["recall"]), float(shifted_metrics["recall"])),
        "f1": comparison(float(healthy_metrics["f1"]), float(shifted_metrics["f1"])),
        "false_positive_rate": comparison(
            float(healthy_metrics["false_positive_rate"]),
            float(shifted_metrics["false_positive_rate"]),
            lower_is_better=True,
        ),
        "validation_average_precision_without_changed_feature": ablated_ap,
        "validation_average_precision_delta": (
            float(validation_results[selected_name]["average_precision"]) - ablated_ap
        ),
    }
    prevalence = float(splits.train["is_fraud"].mean())
    gates = {
        "model_beats_prevalence": (
            float(healthy_metrics["average_precision"]) >= prevalence * 1.25
        ),
        "feature_distribution_moves": assessment["changed_feature_psi"] >= 0.2,
        "performance_degrades": (
            max(
                float(assessment[metric]["degradation_percent"])
                for metric in ("recall", "f1", "false_positive_rate")
            )
            >= 5.0
        ),
    }
    manifest = {
        "model": "mobile-money-fraud-detection",
        "selected_estimator": selected_name,
        "threshold": threshold,
        "features": FEATURES,
        "semantic_change": {
            "field": "amount",
            "healthy_scale_multiplier": 1,
            "released_scale_multiplier": 100,
            "failure_mode": "an uncoordinated feature-unit conversion",
        },
        "sample_rows": len(frame),
        "split_rows": {
            "train": len(splits.train),
            "validation": len(splits.validation),
            "test": len(splits.test),
        },
        "split_boundaries": splits.boundaries,
        "training_prevalence": prevalence,
        "validation": validation_results,
        "test_healthy": healthy_metrics,
        "test_silent_change": shifted_metrics,
        "assessment": assessment,
        "viability_gates": gates,
        "viable": all(gates.values()),
        "limitations": [
            (
                "The source data is synthetic and has a higher fraud prevalence than many "
                "live systems."
            ),
            "The reference model is for reliability demonstrations, not financial decisions.",
        ],
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": selected,
            "threshold": threshold,
            "features": FEATURES,
            "manifest": manifest,
        },
        artifact_path,
    )
    manifest_path.write_text(json.dumps(_jsonable(manifest), indent=2, sort_keys=True) + "\n")
    return manifest


def _load_sample(path: Path, max_rows: int) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Prepared dataset not found: {path}")
    connection = duckdb.connect()
    try:
        return connection.execute(
            """
            SELECT * FROM read_parquet(?)
            ORDER BY hash(step, initiator, recipient, amount)
            LIMIT ?
            """,
            [str(path), max_rows],
        ).fetch_df()
    finally:
        connection.close()


def _temporal_split(frame: pd.DataFrame, label_delay_hours: int = 24) -> SplitFrames:
    minimum = float(frame["step"].min())
    maximum = float(frame["step"].max())
    span = maximum - minimum
    train_end = minimum + span * 0.55
    validation_start = train_end + label_delay_hours
    validation_end = minimum + span * 0.75
    test_start = validation_end + label_delay_hours
    train = frame[frame["step"] <= train_end].copy()
    validation = frame[
        (frame["step"] >= validation_start) & (frame["step"] <= validation_end)
    ].copy()
    test = frame[frame["step"] >= test_start].copy()
    if min(len(train), len(validation), len(test)) < 100:
        raise ValueError("Temporal split produced fewer than 100 rows in a partition")
    return SplitFrames(
        train=train,
        validation=validation,
        test=test,
        boundaries={
            "minimum_step": minimum,
            "train_end": train_end,
            "validation_start": validation_start,
            "validation_end": validation_end,
            "test_start": test_start,
            "maximum_step": maximum,
            "label_delay_hours": float(label_delay_hours),
        },
    )


def _pipeline(
    name: Literal["logistic_regression", "hist_gradient_boosting"] | str,
    random_state: int,
    features: list[str],
) -> Pipeline:
    numeric = [feature for feature in NUMERIC_FEATURES if feature in features]
    categorical = [feature for feature in CATEGORICAL_FEATURES if feature in features]
    if name == "logistic_regression":
        preprocessor = ColumnTransformer(
            [
                ("numeric", StandardScaler(), numeric),
                ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
            ]
        )
        estimator = LogisticRegression(
            class_weight="balanced", max_iter=500, random_state=random_state
        )
    else:
        preprocessor = ColumnTransformer(
            [
                ("numeric", "passthrough", numeric),
                (
                    "categorical",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                    categorical,
                ),
            ],
            sparse_threshold=0,
        )
        estimator = HistGradientBoostingClassifier(
            class_weight="balanced",
            learning_rate=0.08,
            max_iter=160,
            max_leaf_nodes=31,
            l2_regularization=0.1,
            early_stopping=True,
            random_state=random_state,
        )
    return Pipeline([("preprocessor", preprocessor), ("classifier", estimator)])


def _logistic_pipeline(random_state: int) -> Pipeline:
    return _pipeline("logistic_regression", random_state, FEATURES)


def _boosting_pipeline(random_state: int) -> Pipeline:
    return _pipeline("hist_gradient_boosting", random_state, FEATURES)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value
