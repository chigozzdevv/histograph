import hashlib
import hmac
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from histograph_api.routes.github import _mapped_assets, _push_changed_files
from histograph_api.schemas.github import AssetMapping
from histograph_github import GitHubAppClient, verify_webhook_signature
from pydantic import ValidationError


def test_webhook_signature_requires_matching_sha256_digest() -> None:
    payload = b'{"action":"opened"}'
    secret = "webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(payload, signature, secret)
    assert not verify_webhook_signature(payload + b" ", signature, secret)
    assert not verify_webhook_signature(payload, "sha1=invalid", secret)
    assert not verify_webhook_signature(payload, None, secret)


def test_asset_mapping_requires_datahub_urns_and_deduplicates_values() -> None:
    mapping = AssetMapping(
        pattern="models/revenue/*.sql",
        asset_urns=("urn:li:dataset:(snowflake,revenue,PROD)",) * 2,
    )
    assert mapping.asset_urns == ("urn:li:dataset:(snowflake,revenue,PROD)",)

    with pytest.raises(ValidationError):
        AssetMapping(pattern="*.sql", asset_urns=("warehouse.revenue",))


def test_changed_files_map_to_unique_assets() -> None:
    payload = {
        "commits": [
            {
                "added": ["models/revenue/orders.sql"],
                "modified": ["models/revenue/orders.sql", "README.md"],
                "removed": [],
            }
        ]
    }
    files = _push_changed_files(payload)
    assets = _mapped_assets(
        {
            "asset_mappings": [
                {
                    "pattern": "models/revenue/*.sql",
                    "asset_urns": ["urn:li:dataset:(snowflake,revenue.orders,PROD)"],
                },
                {
                    "pattern": "models/**/*.sql",
                    "asset_urns": ["urn:li:dataset:(snowflake,revenue.orders,PROD)"],
                },
            ]
        },
        files,
    )

    assert files == ("models/revenue/orders.sql", "README.md")
    assert assets == ("urn:li:dataset:(snowflake,revenue.orders,PROD)",)


@pytest.mark.asyncio
async def test_github_app_uses_signed_jwt_and_reuses_installation_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if request.url.path == "/app/installations/42/access_tokens":
            token_requests += 1
            encoded = request.headers["Authorization"].removeprefix("Bearer ")
            claims = jwt.decode(encoded, public_pem, algorithms=["RS256"])
            assert claims["iss"] == "12345"
            assert 540 <= claims["exp"] - int(datetime.now(UTC).timestamp()) <= 550
            assert 55 <= int(datetime.now(UTC).timestamp()) - claims["iat"] <= 65
            return httpx.Response(
                201,
                json={"token": "installation-token", "expires_at": "2099-01-01T00:00:00Z"},
            )
        if request.url.path == "/installation/repositories":
            assert request.headers["Authorization"] == "Bearer installation-token"
            return httpx.Response(200, json={"repositories": [{"id": 7, "name": "analytics"}]})
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github = GitHubAppClient(
        app_id="12345",
        private_key=private_pem,
        http_client=http_client,
    )
    try:
        assert len(await github.list_repositories(42)) == 1
        assert len(await github.list_repositories(42)) == 1
        assert token_requests == 1
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_ensure_check_run_recovers_existing_external_id() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    post_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_requests
        if request.url.path == "/app/installations/42/access_tokens":
            return httpx.Response(
                201,
                json={"token": "installation-token", "expires_at": "2099-01-01T00:00:00Z"},
            )
        if request.method == "GET" and request.url.path.endswith("/check-runs"):
            return httpx.Response(
                200,
                json={"check_runs": [{"id": 88, "external_id": "run-123"}]},
            )
        if request.method == "POST":
            post_requests += 1
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    github = GitHubAppClient(
        app_id="12345",
        private_key=private_pem,
        http_client=http_client,
    )
    try:
        check_id = await github.ensure_check_run(
            installation_id=42,
            owner="acme",
            repository="analytics",
            head_sha="abc123",
            external_id="run-123",
            details_url="https://histograph.example/runs/run-123",
        )
        assert check_id == 88
        assert post_requests == 0
    finally:
        await http_client.aclose()
