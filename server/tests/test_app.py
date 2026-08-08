from histograph.api.app import create_app
from histograph.settings import Settings


def test_app_factory_does_not_require_live_storage() -> None:
    app = create_app(Settings())

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/v1/events/predictions" in paths
    assert "/v1/models/{model_name}" in paths
