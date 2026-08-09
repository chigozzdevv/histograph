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
        feature="merchant_velocity",
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


def test_feature_drift_comparison_treats_increasing_psi_as_degradation() -> None:
    telemetry = FakeTelemetry(feature_windows=[[1.0] * 10, [10.0] * 10])
    monitor = Monitor(
        model="fraud",
        version="v1",
        signal="feature_drift",
        metric="psi",
        feature="amount",
        operator="gt",
        threshold=0.2,
        minimum_sample_size=10,
    )

    result, _ = DetectionEngine(telemetry).evaluate_feature_drift(
        uuid4(), monitor, "amount", datetime(2026, 8, 8, tzinfo=UTC)
    )

    assert result.triggered is True
    assert result.comparison["direction"] == "degraded"


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
    assert result.comparison["absolute_change_percentage_points"] == -50.0
    assert result.comparison["relative_change_percent"] == -50.0
    assert result.comparison["degradation_percent"] == 50.0
    assert result.comparison["direction"] == "degraded"
    assert result.triggered is True
    assert event is not None


def test_directional_performance_monitor_only_triggers_on_degradation() -> None:
    model = ModelDefinition(
        name="fraud",
        task="binary_classification",
        positive_class="blocked",
        positive_actual="chargeback",
    )
    monitor = Monitor(
        model="fraud",
        version="v1",
        signal="performance",
        metric="recall",
        operator="decrease",
        threshold=0.2,
        minimum_sample_size=4,
    )
    degrading = FakeTelemetry(
        binary_windows=[
            [(True, True), (True, True), (False, False), (False, False)],
            [(True, True), (False, True), (False, False), (False, False)],
        ]
    )
    improving = FakeTelemetry(
        binary_windows=[
            [(True, True), (False, True), (False, False), (False, False)],
            [(True, True), (True, True), (False, False), (False, False)],
        ]
    )

    degraded, degraded_event = DetectionEngine(degrading).evaluate_performance(
        uuid4(), monitor, model, datetime(2026, 8, 8, tzinfo=UTC)
    )
    improved, improved_event = DetectionEngine(improving).evaluate_performance(
        uuid4(), monitor, model, datetime(2026, 8, 8, tzinfo=UTC)
    )

    assert degraded.triggered is True
    assert degraded.comparison["degradation_percent"] == 50.0
    assert degraded_event is not None
    assert improved.triggered is False
    assert improved.comparison["direction"] == "improved"
    assert improved_event is None


def test_canary_performance_compares_candidate_and_reference_in_the_same_window() -> None:
    telemetry = FakeTelemetry(
        binary_windows=[
            [(True, True), (True, True), (False, False), (False, False)],
            [(True, True), (False, True), (False, False), (False, False)],
        ]
    )
    monitor = Monitor(
        model="fraud",
        version="v2",
        reference_version="v1",
        signal="performance",
        metric="recall",
        operator="decrease",
        threshold=0.2,
        minimum_sample_size=4,
    )
    model = ModelDefinition(
        name="fraud",
        task="binary_classification",
        positive_class="blocked",
        positive_actual="chargeback",
    )

    result, event = DetectionEngine(telemetry).evaluate_performance_against_version(
        uuid4(), monitor, model, "v1", datetime(2026, 8, 8, tzinfo=UTC)
    )

    assert result.triggered is True
    assert result.baseline_value == 1.0
    assert result.observed_value == 0.5
    assert result.evidence["reference"]["version"] == "v1"
    assert result.evidence["candidate"]["version"] == "v2"
    assert event is not None
