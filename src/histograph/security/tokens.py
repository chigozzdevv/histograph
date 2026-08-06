import hashlib
import hmac
import secrets
from dataclasses import dataclass

from histograph.security.errors import SecurityConfigurationError


@dataclass(frozen=True)
class IssuedToken:
    plaintext: str
    prefix: str
    digest: str


class TokenManager:
    def __init__(self, pepper: str):
        if len(pepper) < 32:
            raise SecurityConfigurationError("Token pepper must contain at least 32 characters")
        self._pepper = pepper.encode()

    def issue(self) -> IssuedToken:
        plaintext = f"hst_{secrets.token_urlsafe(36)}"
        return IssuedToken(
            plaintext=plaintext,
            prefix=plaintext[:16],
            digest=self.digest(plaintext),
        )

    def digest(self, plaintext: str) -> str:
        return hmac.new(self._pepper, plaintext.encode(), hashlib.sha256).hexdigest()

    def matches(self, plaintext: str, expected_digest: str) -> bool:
        return hmac.compare_digest(self.digest(plaintext), expected_digest)
