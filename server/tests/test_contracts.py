from datetime import datetime

import pytest
from pydantic import ValidationError

from histograph.monitors.types import Monitor
from histograph.telemetry.types import Prediction


def test_prediction_normalizes_naive_timestamp_to_utc() -> None:
    prediction = Prediction(
        prediction_id="p-1",
        model="fraud-detection",
        version="v1",
        observed_at=datetime(2026, 8, 7, 9, 0),
        predicted_class="fraud",
        score=0.8,
    )

    assert prediction.observed_at.tzinfo is not None
    assert prediction.observed_at.isoformat() == "2026-08-07T09:00:00+00:00"


def test_prediction_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Prediction.model_validate(
            {
                "prediction_id": "p-1",
                "model": "fraud-detection",
                "version": "v1",
                "observed_at": datetime(2026, 8, 7, 9, 0),
                "unexpected": "value",
            }
        )


def test_monitor_rejects_unimplemented_signal() -> None:
    with pytest.raises(ValidationError):
        Monitor.model_validate(
            {
                "model": "fraud",
                "version": "v1",
                "signal": "operational",
                "metric": "latency",
                "operator": "gt",
                "threshold": 100,
            }
        )


def test_feature_drift_monitor_requires_psi_semantics() -> None:
    with pytest.raises(ValidationError):
        Monitor(
            model="fraud",
            version="v1",
            signal="feature_drift",
            metric="accuracy",
            operator="lt",
            threshold=0.2,
        )
