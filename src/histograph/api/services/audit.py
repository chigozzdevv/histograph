from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import AuditEventRecord
from histograph.api.security import Actor
from histograph.security import stable_fingerprint


def add_audit_event(
    session: AsyncSession,
    *,
    actor: Actor,
    organization_id: str,
    action: str,
    target_type: str,
    target_id: str,
    request_id: str,
    project_id: str | None = None,
    source_ip: str | None = None,
    before: Any = None,
    after: Any = None,
    details: dict[str, Any] | None = None,
) -> AuditEventRecord:
    event = AuditEventRecord(
        organization_id=organization_id,
        project_id=project_id,
        actor_type=actor.type.value,
        actor_id=actor.subject,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        source_ip=source_ip,
        before_fingerprint=_fingerprint(before),
        after_fingerprint=_fingerprint(after),
        details_json=details or {},
    )
    session.add(event)
    return event


def _fingerprint(value: Any) -> str | None:
    return stable_fingerprint(value) if value is not None else None
