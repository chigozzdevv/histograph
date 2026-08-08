from datetime import datetime

import pytest
from pydantic import ValidationError

from histograph.contracts.events import Prediction


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
