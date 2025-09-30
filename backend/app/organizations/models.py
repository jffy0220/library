"""Typed representations of organizations and their memberships."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..entitlements.models import MembershipRole


class OrganizationPolicyFlags(BaseModel):
    """Structured policy flag container stored alongside an organization."""

    sharing_enabled: bool = Field(
        default=True,
        description="Controls whether members can share resources outside the organization.",
    )
    external_exports_allowed: bool = Field(
        default=False,
        description="Allows exports outside of the organization if enabled.",
    )
    retention_days: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional content retention period. None inherits global defaults.",
    )

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class Organization(BaseModel):
    """Persistent organization record bound to a subscription."""

    id: str
    name: str
    owner_id: str = Field(description="Current owner with irrevocable billing authority.")
    billing_contact_id: str
    subscription_id: Optional[str] = Field(
        default=None,
        description="Identifier of the active Team subscription, if any.",
    )
    policy_flags: OrganizationPolicyFlags = Field(
        default_factory=OrganizationPolicyFlags,
        description="Structured policy toggles that govern sharing and retention.",
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class MembershipStatus(str, Enum):
    """Lifecycle state for an organization membership."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class OrganizationMembership(BaseModel):
    """Represents a user's membership inside an organization."""

    id: Optional[str]
    organization_id: str
    user_id: str
    role: MembershipRole = MembershipRole.MEMBER
    status: MembershipStatus = MembershipStatus.ACTIVE
    billing_admin: bool = Field(
        default=False,
        description="Allows the member to perform billing operations without being owner.",
    )
    invited_by: Optional[str] = Field(
        default=None,
        description="Identifier of the inviter when the membership originated from an invite.",
    )
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @property
    def consumes_seat(self) -> bool:
        """Return whether the membership should count against seat allocations."""

        return self.status == MembershipStatus.ACTIVE


class MembershipInvitation(BaseModel):
    """Represents a pending invitation awaiting acceptance."""

    token: str
    organization_id: str
    email: str
    role: MembershipRole
    inviter_id: str
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @field_validator("expires_at")
    @classmethod
    def _validate_expiration(cls, expires_at: datetime, info):  # type: ignore[override]
        created_at = info.data.get("created_at")
        if created_at and expires_at <= created_at:
            raise ValueError("expires_at must be in the future")
        return expires_at


class MembershipAuditAction(str, Enum):
    """Actions that appear in membership related audit logs."""

    INVITED = "invite"
    ACCEPTED = "accept"
    REMOVED = "remove"
    ROLE_CHANGED = "role_change"
    TRANSFER_REQUESTED = "transfer_request"
    TRANSFER_COMPLETED = "transfer_complete"


class MembershipAuditEvent(BaseModel):
    """Structured payload captured in the audit log service."""

    organization_id: str
    actor_id: str
    subject_id: str
    action: MembershipAuditAction
    role_before: Optional[MembershipRole] = None
    role_after: Optional[MembershipRole] = None
    timestamp: datetime
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, frozen=True)