from histograph.api.app import create_app
from histograph.settings import Settings


def test_app_factory_does_not_require_live_storage() -> None:
    app = create_app(Settings())

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/v1/events/predictions" in paths
    assert "/v1/events/predictions/batch" in paths
    assert "/v1/events/actuals/batch" in paths
    assert "/v1/events/changes" in paths
    assert "/v1/models/{model_name}" in paths
    assert "/v1/actions/{action_id}/approval" in paths
    assert "/v1/actions/{action_id}/result" in paths
    assert "/v1/overview" in paths
    assert "/v1/deployments" in paths
    assert "/v1/deployments/{deployment_id}/predict" in paths
    assert "/v1/deployments/{deployment_id}/compare" in paths
    assert "/v1/activity" in paths
    assert "/v1/demo/scenarios" in paths
