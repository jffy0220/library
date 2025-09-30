from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.organizations.models import (
    MembershipAuditAction,
    MembershipInvitation,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from backend.app.organizations.service import (
    AuditLogger,
    EntitlementInvalidator,
    InvitationTokenGenerator,
    OrganizationRepository,
    OrganizationService,
    SeatEventPublisher,
)
from backend.app.entitlements.models import MembershipRole


class InMemoryOrganizationRepository(OrganizationRepository):
    def __init__(self) -> None:
        self.organizations: Dict[str, Organization] = {}
        self.memberships: Dict[Tuple[str, str], OrganizationMembership] = {}
        self.invitations: Dict[str, MembershipInvitation] = {}

    def get_organization(self, organization_id: str) -> Organization:
        try:
            return self.organizations[organization_id]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise LookupError("Organization not found") from exc

    def get_membership(self, organization_id: str, user_id: str) -> Optional[OrganizationMembership]:
        return self.memberships.get((organization_id, user_id))

    def save_membership(self, membership: OrganizationMembership) -> OrganizationMembership:
        assigned = membership
        if membership.id is None:
            new_id = f"m-{len(self.memberships) + 1}"
            assigned = membership.model_copy(update={"id": new_id})
        self.memberships[(assigned.organization_id, assigned.user_id)] = assigned
        return assigned

    def delete_membership(self, organization_id: str, user_id: str) -> None:
        self.memberships.pop((organization_id, user_id), None)

    def create_invitation(self, invitation: MembershipInvitation) -> MembershipInvitation:
        self.invitations[invitation.token] = invitation
        return invitation

    def get_invitation(self, token: str) -> Optional[MembershipInvitation]:
        return self.invitations.get(token)

    def delete_invitation(self, token: str) -> None:
        self.invitations.pop(token, None)


class InMemoryAuditLogger(AuditLogger):
    def __init__(self) -> None:
        self.events: List[MembershipAuditEvent] = []

    def log(self, event: MembershipAuditEvent) -> None:
        self.events.append(event)


class RecordingSeatPublisher(SeatEventPublisher):
    def __init__(self) -> None:
        self.enqueued: List[str] = []

    def enqueue(self, organization_id: str) -> None:
        self.enqueued.append(organization_id)


class StaticTokenGenerator(InvitationTokenGenerator):
    def __init__(self) -> None:
        self.counter = 0

    def generate(self, organization_id: str, email: str, expires_at: datetime) -> str:
        self.counter += 1
        return f"token-{self.counter}"

class RecordingEntitlementInvalidator(EntitlementInvalidator):
    def __init__(self) -> None:
        self.user_ids: List[str] = []
        self.organization_ids: List[str] = []
        self.subscription_ids: List[str] = []

    def invalidate_user(self, user_id: str) -> None:
        self.user_ids.append(user_id)

    def invalidate_organization(self, organization_id: str) -> None:
        self.organization_ids.append(organization_id)

    def invalidate_subscription(self, subscription_id: str) -> None:
        self.subscription_ids.append(subscription_id)

def _fixed_clock() -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.fixture()
def service_components() -> Tuple[
    OrganizationService,
    InMemoryOrganizationRepository,
    InMemoryAuditLogger,
    RecordingSeatPublisher,
    RecordingEntitlementInvalidator,
]:
    repository = InMemoryOrganizationRepository()
    audit_logger = InMemoryAuditLogger()
    seat_publisher = RecordingSeatPublisher()
    token_generator = StaticTokenGenerator()
    entitlement_invalidator = RecordingEntitlementInvalidator()
    service = OrganizationService(
        repository=repository,
        audit_logger=audit_logger,
        seat_publisher=seat_publisher,
        token_generator=token_generator,
        entitlement_invalidator=entitlement_invalidator,
        clock=_fixed_clock,
        invitation_ttl=timedelta(days=7),
    )
    return service, repository, audit_logger, seat_publisher, entitlement_invalidator


def _seed_organization(repository: InMemoryOrganizationRepository) -> Organization:
    organization = Organization(
        id="org-1",
        name="Test Org",
        owner_id="owner-1",
        billing_contact_id="owner-1",
        subscription_id="sub-1",
        created_at=_fixed_clock(),
        updated_at=_fixed_clock(),
    )
    repository.organizations[organization.id] = organization
    repository.save_membership(
        OrganizationMembership(
            id="m-1",
            organization_id=organization.id,
            user_id="owner-1",
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
            accepted_at=_fixed_clock(),
        )
    )
    return organization


def test_admin_cannot_invite_owner_role(
    service_components: Tuple[
        OrganizationService,
        InMemoryOrganizationRepository,
        InMemoryAuditLogger,
        RecordingSeatPublisher,
        RecordingEntitlementInvalidator,
    ]
):
    service, repository, audit_logger, _, _ = service_components
    organization = _seed_organization(repository)
    repository.save_membership(
        OrganizationMembership(
            id="m-2",
            organization_id=organization.id,
            user_id="admin-1",
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            accepted_at=_fixed_clock(),
        )
    )

    with pytest.raises(PermissionError):
        service.invite_member(
            organization_id=organization.id,
            inviter_id="admin-1",
            email="new-owner@example.com",
            role=MembershipRole.OWNER,
        )

    assert [event.action for event in audit_logger.events] == []


def test_accept_invitation_consumes_seat_and_logs(
    service_components: Tuple[
        OrganizationService,
        InMemoryOrganizationRepository,
        InMemoryAuditLogger,
        RecordingSeatPublisher,
        RecordingEntitlementInvalidator,
    ]
):
    service, repository, audit_logger, seat_publisher, entitlement_invalidator = service_components
    organization = _seed_organization(repository)
    invitation = service.invite_member(
        organization_id=organization.id,
        inviter_id="owner-1",
        email="member@example.com",
        role=MembershipRole.MEMBER,
    )

    membership = service.accept_invitation(invitation.token, user_id="user-123")

    assert membership.status == MembershipStatus.ACTIVE
    assert membership.organization_id == organization.id
    assert repository.get_membership(organization.id, "user-123").consumes_seat is True
    assert seat_publisher.enqueued == [organization.id]
    assert entitlement_invalidator.user_ids == ["user-123"]
    assert entitlement_invalidator.organization_ids == [organization.id]
    assert entitlement_invalidator.subscription_ids == [organization.subscription_id]
    assert [event.action for event in audit_logger.events] == [
        MembershipAuditAction.INVITED,
        MembershipAuditAction.ACCEPTED,
    ]


def test_remove_member_revokes_and_triggers_reconciliation(
    service_components: Tuple[
        OrganizationService,
        InMemoryOrganizationRepository,
        InMemoryAuditLogger,
        RecordingSeatPublisher,
        RecordingEntitlementInvalidator,
    ]
):
    service, repository, audit_logger, seat_publisher, entitlement_invalidator = service_components
    organization = _seed_organization(repository)
    repository.save_membership(
        OrganizationMembership(
            id="m-3",
            organization_id=organization.id,
            user_id="member-1",
            role=MembershipRole.MEMBER,
            status=MembershipStatus.ACTIVE,
            accepted_at=_fixed_clock(),
        )
    )

    updated = service.remove_member(organization.id, actor_id="owner-1", target_user_id="member-1")

    assert updated.status == MembershipStatus.REVOKED
    assert repository.get_membership(organization.id, "member-1").status == MembershipStatus.REVOKED
    assert seat_publisher.enqueued[-1] == organization.id
    assert audit_logger.events[-1].action == MembershipAuditAction.REMOVED
    assert entitlement_invalidator.user_ids[-1] == "member-1"
    assert entitlement_invalidator.organization_ids[-1] == organization.id
    assert entitlement_invalidator.subscription_ids[-1] == organization.subscription_id


def test_role_change_requires_owner_for_promotion(
    service_components: Tuple[
        OrganizationService,
        InMemoryOrganizationRepository,
        InMemoryAuditLogger,
        RecordingSeatPublisher,
        RecordingEntitlementInvalidator,
    ]
):
    service, repository, _, _, entitlement_invalidator = service_components
    organization = _seed_organization(repository)
    repository.save_membership(
        OrganizationMembership(
            id="m-4",
            organization_id=organization.id,
            user_id="admin-1",
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
            accepted_at=_fixed_clock(),
        )
    )

    with pytest.raises(PermissionError):
        service.change_role(
            organization_id=organization.id,
            actor_id="admin-1",
            target_user_id="owner-1",
            new_role=MembershipRole.ADMIN,
        )

    with pytest.raises(PermissionError):
        service.change_role(
            organization_id=organization.id,
            actor_id="admin-1",
            target_user_id="owner-1",
            new_role=MembershipRole.MEMBER,
        )

    with pytest.raises(PermissionError):
        service.change_role(
            organization_id=organization.id,
            actor_id="admin-1",
            target_user_id="admin-1",
            new_role=MembershipRole.OWNER,
        )

    owner_updated = service.change_role(
        organization_id=organization.id,
        actor_id="owner-1",
        target_user_id="admin-1",
        new_role=MembershipRole.MEMBER,
    )

    assert owner_updated.role == MembershipRole.MEMBER
    assert entitlement_invalidator.user_ids[-1] == "admin-1"
    assert entitlement_invalidator.organization_ids[-1] == organization.id
    assert entitlement_invalidator.subscription_ids[-1] == organization.subscription_id