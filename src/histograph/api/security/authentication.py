from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from histograph.api.config import Settings
from histograph.api.database.models import ServiceIdentityRecord
from histograph.api.security.actors import Actor, ActorType
from histograph.api.security.oidc import OidcValidationError, OidcValidator
from histograph.security import TokenManager

_bearer = HTTPBearer(auto_error=False)


class Authenticator:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        token_manager: TokenManager,
    ):
        self._bootstrap_token = (
            settings.bootstrap_token.get_secret_value() if settings.bootstrap_token else None
        )
        self._session_factory = session_factory
        self._token_manager = token_manager
        self._oidc = (
            OidcValidator(settings.oidc_issuer, settings.oidc_audience)
            if settings.oidc_issuer and settings.oidc_audience
            else None
        )

    async def authenticate(self, token: str) -> Actor:
        if self._bootstrap_token and token == self._bootstrap_token:
            return Actor(type=ActorType.BOOTSTRAP, subject="bootstrap", scopes=frozenset({"*"}))
        if token.startswith("hst_"):
            return await self._authenticate_service(token)
        if self._oidc is not None:
            return await self._authenticate_oidc(token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    async def _authenticate_service(self, token: str) -> Actor:
        digest = self._token_manager.digest(token)
        async with self._session_factory() as session:
            record = await session.scalar(
                select(ServiceIdentityRecord).where(
                    ServiceIdentityRecord.token_digest == digest,
                    ServiceIdentityRecord.revoked_at.is_(None),
                    ServiceIdentityRecord.deleted_at.is_(None),
                )
            )
        if record is None or (record.expires_at and record.expires_at <= datetime.now(UTC)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token"
            )
        return Actor(
            type=ActorType.SERVICE,
            subject=record.id,
            organization_id=record.organization_id,
            project_id=record.project_id,
            scopes=frozenset(record.scopes_json),
        )

    async def _authenticate_oidc(self, token: str) -> Actor:
        try:
            claims = await self._oidc.validate(token) if self._oidc else {}
        except (OidcValidationError, httpx.HTTPError) as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token"
            ) from error
        scope_value = claims.get("scope", "")
        scopes = frozenset(scope_value.split()) if isinstance(scope_value, str) else frozenset()
        return Actor(
            type=ActorType.USER,
            subject=str(claims["sub"]),
            scopes=scopes,
            claims=claims,
        )


async def get_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Actor:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    return await request.app.state.authenticator.authenticate(credentials.credentials)


def require_scope(scope: str):
    async def dependency(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        if not actor.has_scope(scope):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient scope")
        return actor

    return dependency
