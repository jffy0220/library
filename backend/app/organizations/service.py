"""Service layer orchestrating organization and membership operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from ..entitlements.models import MembershipRole
from .models import (
    MembershipAuditAction,
    MembershipAuditEvent,
    MembershipInvitation,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)


class OrganizationRepository(Protocol):
    """Persistence layer for organizations and memberships."""

    def get_organization(self, organization_id: str) -> Organization:
        ...

    def get_membership(self, organization_id: str, user_id: str) -> Optional[OrganizationMembership]:
        ...

    def save_membership(self, membership: OrganizationMembership) -> OrganizationMembership:
        ...

    def delete_membership(self, organization_id: str, user_id: str) -> None:
        ...

    def create_invitation(self, invitation: MembershipInvitation) -> MembershipInvitation:
        ...

    def get_invitation(self, token: str) -> Optional[MembershipInvitation]:
        ...

    def delete_invitation(self, token: str) -> None:
        ...


class AuditLogger(Protocol):
    """Interface for emitting audit events."""

    def log(self, event: MembershipAuditEvent) -> None:
        ...


class SeatEventPublisher(Protocol):
    """Interface for notifying downstream billing/seat reconciliation."""

    def enqueue(self, organization_id: str) -> None:
        ...


class InvitationTokenGenerator(Protocol):
    """Generates signed invitation tokens."""

    def generate(self, organization_id: str, email: str, expires_at: datetime) -> str:
        ...


class EntitlementInvalidator(Protocol):
    """Interface for invalidating entitlement cache entries."""

    def invalidate_user(self, user_id: str) -> None:
        ...

    def invalidate_organization(self, organization_id: str) -> None:
        ...

    def invalidate_subscription(self, subscription_id: str) -> None:
        ...


ROLE_HIERARCHY = {
    MembershipRole.MEMBER: 1,
    MembershipRole.ADMIN: 2,
    MembershipRole.OWNER: 3,
}


def _role_allows_assignment(actor_role: MembershipRole, target_role: MembershipRole) -> bool:
    """Return whether a role can assign the target role."""

    return ROLE_HIERARCHY[actor_role] >= ROLE_HIERARCHY[target_role]


def _current_time(clock: Optional[Callable[[], datetime]]) -> datetime:
    if clock is None:
        return datetime.now(timezone.utc)
    value = clock()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class OrganizationService:
    """Coordinates repository access and domain invariants for organizations."""

    repository: OrganizationRepository
    audit_logger: AuditLogger
    seat_publisher: SeatEventPublisher
    token_generator: InvitationTokenGenerator
    entitlement_invalidator: EntitlementInvalidator
    clock: Optional[Callable[[], datetime]] = None
    invitation_ttl: timedelta = timedelta(days=7)

    def invite_member(
        self,
        organization_id: str,
        inviter_id: str,
        email: str,
        role: MembershipRole,
        *,
        expires_at: Optional[datetime] = None,
    ) -> MembershipInvitation:
        organization = self.repository.get_organization(organization_id)
        inviter_membership = self._require_active_membership(organization_id, inviter_id)

        if not _role_allows_assignment(inviter_membership.role, role):
            raise PermissionError("Inviter does not have permission to assign the requested role")

        now = _current_time(self.clock)
        invitation_expires_at = expires_at or now + self.invitation_ttl
        token = self.token_generator.generate(organization.id, email, invitation_expires_at)
        invitation = MembershipInvitation(
            token=token,
            organization_id=organization.id,
            email=email,
            role=role,
            inviter_id=inviter_membership.user_id,
            created_at=now,
            expires_at=invitation_expires_at,
        )
        stored_invitation = self.repository.create_invitation(invitation)
        self.audit_logger.log(
            MembershipAuditEvent(
                organization_id=organization.id,
                actor_id=inviter_membership.user_id,
                subject_id=email,
                action=MembershipAuditAction.INVITED,
                timestamp=now,
                metadata={"role": role.value},
            )
        )
        return stored_invitation

    def accept_invitation(self, token: str, user_id: str) -> OrganizationMembership:
        invitation = self.repository.get_invitation(token)
        if invitation is None:
            raise LookupError("Invitation not found")

        organization = self.repository.get_organization(invitation.organization_id)
        now = _current_time(self.clock)
        if invitation.expires_at <= now:
            raise PermissionError("Invitation has expired")

        existing_membership = self.repository.get_membership(invitation.organization_id, user_id)
        membership = OrganizationMembership(
            id=existing_membership.id if existing_membership else None,
            organization_id=invitation.organization_id,
            user_id=user_id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
            invited_by=invitation.inviter_id,
            invited_at=invitation.created_at,
            accepted_at=now,
            revoked_at=None,
        )
        stored_membership = self.repository.save_membership(membership)
        self.repository.delete_invitation(invitation.token)
        self.audit_logger.log(
            MembershipAuditEvent(
                organization_id=invitation.organization_id,
                actor_id=user_id,
                subject_id=user_id,
                action=MembershipAuditAction.ACCEPTED,
                role_after=stored_membership.role,
                timestamp=now,
                metadata={"invited_by": invitation.inviter_id},
            )
        )
        self._invalidate_entitlements(organization, stored_membership.user_id)
        self.seat_publisher.enqueue(invitation.organization_id)
        return stored_membership

    def remove_member(self, organization_id: str, actor_id: str, target_user_id: str) -> OrganizationMembership:
        organization = self.repository.get_organization(organization_id)
        actor_membership = self._require_active_membership(organization_id, actor_id)
        target_membership = self._require_membership(organization_id, target_user_id)

        if target_membership.role == MembershipRole.OWNER and actor_membership.role != MembershipRole.OWNER:
            raise PermissionError("Only an owner can remove another owner")
        if ROLE_HIERARCHY[actor_membership.role] <= ROLE_HIERARCHY[target_membership.role] and actor_id != target_user_id:
            raise PermissionError("Insufficient privileges to remove this member")

        now = _current_time(self.clock)
        updated_membership = target_membership.model_copy(
            update={
                "status": MembershipStatus.REVOKED,
                "revoked_at": now,
            }
        )
        stored_membership = self.repository.save_membership(updated_membership)
        self.audit_logger.log(
            MembershipAuditEvent(
                organization_id=organization_id,
                actor_id=actor_id,
                subject_id=target_user_id,
                action=MembershipAuditAction.REMOVED,
                role_before=target_membership.role,
                timestamp=now,
            )
        )
        self._invalidate_entitlements(organization, target_user_id)
        self.seat_publisher.enqueue(organization_id)
        return stored_membership

    def change_role(
        self,
        organization_id: str,
        actor_id: str,
        target_user_id: str,
        new_role: MembershipRole,
    ) -> OrganizationMembership:
        organization = self.repository.get_organization(organization_id)
        actor_membership = self._require_active_membership(organization_id, actor_id)
        target_membership = self._require_membership(organization_id, target_user_id)

        if target_membership.role == MembershipRole.OWNER and actor_membership.role != MembershipRole.OWNER:
            raise PermissionError("Only an owner may change another owner's role")
        if new_role == MembershipRole.OWNER and actor_membership.role != MembershipRole.OWNER:
            raise PermissionError("Only an owner may promote another member to owner")
        if not _role_allows_assignment(actor_membership.role, new_role):
            raise PermissionError("Insufficient privileges to assign the requested role")

        now = _current_time(self.clock)
        updated_membership = target_membership.model_copy(update={"role": new_role})
        stored_membership = self.repository.save_membership(updated_membership)
        self.audit_logger.log(
            MembershipAuditEvent(
                organization_id=organization_id,
                actor_id=actor_id,
                subject_id=target_user_id,
                action=MembershipAuditAction.ROLE_CHANGED,
                role_before=target_membership.role,
                role_after=new_role,
                timestamp=now,
            )
        )
        self._invalidate_entitlements(organization, target_user_id)
        return stored_membership

    def _require_active_membership(self, organization_id: str, user_id: str) -> OrganizationMembership:
        membership = self._require_membership(organization_id, user_id)
        if membership.status != MembershipStatus.ACTIVE:
            raise PermissionError("Membership is not active")
        return membership

    def _require_membership(self, organization_id: str, user_id: str) -> OrganizationMembership:
        membership = self.repository.get_membership(organization_id, user_id)
        if membership is None:
            raise LookupError("Membership not found")
        return membership

    def _invalidate_entitlements(self, organization: Organization, user_id: Optional[str]) -> None:
        self.entitlement_invalidator.invalidate_organization(organization.id)
        if organization.subscription_id:
            self.entitlement_invalidator.invalidate_subscription(organization.subscription_id)
        if user_id:
            self.entitlement_invalidator.invalidate_user(user_id)