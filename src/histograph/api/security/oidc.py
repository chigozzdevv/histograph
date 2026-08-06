import asyncio
from time import monotonic
from typing import Any

import httpx
import jwt


class OidcValidationError(ValueError):
    pass


class OidcValidator:
    def __init__(self, issuer: str, audience: str, cache_seconds: int = 300):
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def validate(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            if not isinstance(key_id, str) or not key_id:
                raise OidcValidationError("OIDC token does not contain a key identifier")
            key = await self._get_key(key_id)
            return jwt.decode(
                token,
                key=key.key,
                algorithms=[key.algorithm_name],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except OidcValidationError:
            raise
        except jwt.PyJWTError as error:
            raise OidcValidationError("OIDC token could not be verified") from error

    async def _get_key(self, key_id: str) -> jwt.PyJWK:
        expired = monotonic() >= self._expires_at
        if expired or key_id not in self._keys:
            await self._refresh(force=not expired)
        key = self._keys.get(key_id)
        if key is None:
            raise OidcValidationError("OIDC signing key is unavailable")
        return key

    async def _refresh(self, *, force: bool = False) -> None:
        async with self._lock:
            if not force and monotonic() < self._expires_at and self._keys:
                return
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                discovery = await client.get(f"{self._issuer}/.well-known/openid-configuration")
                discovery.raise_for_status()
                jwks_uri = discovery.json().get("jwks_uri")
                if not isinstance(jwks_uri, str):
                    raise OidcValidationError("OIDC discovery did not provide a JWKS URI")
                response = await client.get(jwks_uri)
                response.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(response.json())
            self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
            self._expires_at = monotonic() + self._cache_seconds
