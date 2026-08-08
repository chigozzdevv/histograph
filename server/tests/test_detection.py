from datetime import UTC, datetime
from uuid import uuid4

from histograph.detection.engine import DetectionEngine
from histograph.models.types import ModelDefinition
from histograph.monitors.types import Monitor


class FakeTelemetry:
    def __init__(
        self,
        *,
        feature_windows: list[list[float]] | None = None,
        binary_windows: list[list[tuple[bool, bool]]] | None = None,
    ) -> None:
        self.feature_windows = feature_windows or []
        self.binary_windows = binary_windows or []
        self.binary_mapping: tuple[str, object] | None = None

    def feature_values(self, model, version, feature, start, end):
        return self.feature_windows.pop(0)

    def binary_pairs(
        self,
        model,
        version,
        start,
        end,
        positive_class,
        positive_actual,
    ):
        self.binary_mapping = (positive_class, positive_actual)
        return self.binary_windows.pop(0)


def test_feature_drift_requires_the_configured_minimum_sample_size() -> None:
    telemetry = FakeTelemetry(feature_windows=[[1.0, 2.0], [8.0, 9.0]])
    monitor = Monitor(
        model="fraud",
        version="v1",
        signal="feature_drift",
        metric="psi",
        operator="gt",
        threshold=0.2,
        minimum_sample_size=3,
    )

    result, event = DetectionEngine(telemetry).evaluate_feature_drift(
        uuid4(), monitor, "merchant_velocity", datetime(2026, 8, 8, tzinfo=UTC)
    )

    assert result.status == "insufficient_data"
    assert result.observed_value is None
    assert result.triggered is False
    assert event is None


def test_performance_uses_registered_binary_class_mapping() -> None:
    telemetry = FakeTelemetry(
        binary_windows=[
            [(True, True), (False, False)],
            [(True, False), (False, False)],
        ]
    )
    monitor = Monitor(
        model="fraud",
        version="v2",
        signal="performance",
        metric="accuracy",
        operator="lt",
        threshold=0.75,
        minimum_sample_size=2,
    )
    model = ModelDefinition(
        name="fraud",
        task="binary_classification",
        positive_class="blocked",
        positive_actual="chargeback",
    )

    result, event = DetectionEngine(telemetry).evaluate_performance(
        uuid4(), monitor, model, datetime(2026, 8, 8, tzinfo=UTC)
    )

    assert telemetry.binary_mapping == ("blocked", "chargeback")
    assert result.status == "evaluated"
    assert result.observed_value == 0.5
    assert result.triggered is True
    assert event is not None
