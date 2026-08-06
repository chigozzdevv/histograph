from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from histograph.api.database.base import Base
from histograph.api.database.models.common import (
    Role,
    SoftDeleteMixin,
    TimestampMixin,
    enum_type,
    json_type,
    new_id,
)


class OrganizationRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)


class UserRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)


class MembershipRecord(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        Index("ix_memberships_user_organization", "user_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Role] = mapped_column(enum_type(Role, "membership_role"), nullable=False)


class ServiceIdentityRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "service_identities"
    __table_args__ = (Index("ix_service_identities_token_digest", "token_digest", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes_json: Mapped[list[str]] = mapped_column(json_type, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
