from dataclasses import dataclass
from hmac import compare_digest


@dataclass(frozen=True)
class ApprovalPrincipal:
    actor_id: str
    roles: tuple[str, ...] = ("remediation_approver",)


class StaticTokenAuthorizer:
    def __init__(self, identities: dict[str, str]):
        self._identities = identities

    def authorize(self, authorization: str | None) -> ApprovalPrincipal:
        token = _bearer_token(authorization)
        for candidate, actor_id in self._identities.items():
            if compare_digest(token, candidate):
                return ApprovalPrincipal(actor_id=actor_id)
        raise PermissionError("A valid remediation approver token is required")


def authorize_callback(authorization: str | None, expected_token: str | None) -> None:
    if expected_token is None:
        raise PermissionError("Remediation execution callbacks are not configured")
    token = _bearer_token(authorization)
    if not compare_digest(token, expected_token):
        raise PermissionError("A valid remediation callback token is required")


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise PermissionError("Bearer authorization is required")
    scheme, separator, token = authorization.partition(" ")
    if separator == "" or scheme.lower() != "bearer" or not token.strip():
        raise PermissionError("Bearer authorization is required")
    return token.strip()
