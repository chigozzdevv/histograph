import hashlib
import hmac


def authorize_configuration(authorization: str | None, configured_token: str | None) -> None:
    if configured_token is None:
        raise PermissionError("GitHub integration configuration is disabled")
    if authorization is None or not authorization.startswith("Bearer "):
        raise PermissionError("Bearer authorization is required")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not supplied or not hmac.compare_digest(supplied, configured_token):
        raise PermissionError("A valid GitHub configuration token is required")


def verify_webhook_signature(body: bytes, signature: str | None, secret: str | None) -> None:
    if secret is None:
        raise PermissionError("GitHub webhook handling is disabled")
    if signature is None or not signature.startswith("sha256="):
        raise PermissionError("GitHub webhook signature is required")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("GitHub webhook signature is invalid")
