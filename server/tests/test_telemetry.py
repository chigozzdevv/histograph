from histograph.telemetry.repository import _scalars_equal


def test_actual_comparison_does_not_coerce_strings_to_booleans() -> None:
    assert _scalars_equal("false", False) is False
    assert _scalars_equal(False, False) is True


def test_actual_comparison_accepts_equivalent_json_numbers() -> None:
    assert _scalars_equal(1, 1.0) is True
    assert _scalars_equal(True, 1) is False
