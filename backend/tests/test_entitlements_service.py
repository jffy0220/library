from __future__ import annotations

from typing import Dict, Optional, Tuple

import pytest

from backend.app.entitlements import (
    AddOnGrant,
    AddOnType,
    BillingInterval,
    EntitlementService,
    EntitlementSubject,
    HMACTokenSigner,
    InMemoryEntitlementCache,
    MembershipRole,
    OrganizationMembership,
    PlanKey,
    SubscriptionRecord,
    SubscriptionStatus,
)


class FakeSubscriptionRepository:
    def __init__(self) -> None:
        self._records: Dict[str, SubscriptionRecord] = {}

    def add(self, record: SubscriptionRecord) -> None:
        self._records[record.id] = record

    def get_subscription(self, subscription_id: str) -> Optional[SubscriptionRecord]:
        return self._records.get(subscription_id)


class FakeMembershipRepository:
    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], OrganizationMembership] = {}

    def add(self, membership: OrganizationMembership) -> None:
        key = (membership.user_id, membership.organization_id)
        self._records[key] = membership

    def get_membership(self, user_id: str, organization_id: str) -> Optional[OrganizationMembership]:
        return self._records.get((user_id, organization_id))


@pytest.fixture
def repositories() -> Tuple[FakeSubscriptionRepository, FakeMembershipRepository]:
    return FakeSubscriptionRepository(), FakeMembershipRepository()


@pytest.fixture
def entitlement_service(repositories):
    subscription_repo, membership_repo = repositories
    cache = InMemoryEntitlementCache()
    signer = HMACTokenSigner("test-secret")
    service = EntitlementService(
        subscription_repository=subscription_repo,
        membership_repository=membership_repo,
        cache=cache,
        token_signer=signer,
        ttl_seconds=600,
    )
    return service


def test_individual_plan_entitlements(entitlement_service, repositories):
    subscription_repo, _ = repositories
    subscription_repo.add(
        SubscriptionRecord(
            id="sub-pro",
            plan_key=PlanKey.INDIVIDUAL_PRO,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
        )
    )

    subject = EntitlementSubject(user_id="user-1")
    result = entitlement_service.get_entitlements(subject, subscription_id="sub-pro")

    assert result.payload.plan == PlanKey.INDIVIDUAL_PRO
    assert result.payload.feature_flags["ads.disabled"] is True
    assert result.payload.feature_flags["sync.enabled"] is True
    assert result.payload.feature_flags["search.advanced"] is True
    assert result.payload.storage_quota_gb == 100
    assert result.payload.subscription_id == "sub-pro"
    assert result.token


def test_team_admin_entitlements_include_admin_flag(entitlement_service, repositories):
    subscription_repo, membership_repo = repositories
    subscription_repo.add(
        SubscriptionRecord(
            id="sub-team",
            plan_key=PlanKey.TEAM,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
        )
    )
    membership_repo.add(
        OrganizationMembership(
            organization_id="org-1",
            user_id="user-2",
            role=MembershipRole.ADMIN,
        )
    )

    subject = EntitlementSubject(user_id="user-2", organization_id="org-1")
    result = entitlement_service.get_entitlements(subject, subscription_id="sub-team")

    assert result.payload.plan == PlanKey.TEAM
    assert result.payload.role == MembershipRole.ADMIN
    assert result.payload.feature_flags["org.admin"] is True
    assert result.payload.storage_quota_gb == 100


def test_add_on_storage_increment(entitlement_service, repositories):
    subscription_repo, _ = repositories
    subscription_repo.add(
        SubscriptionRecord(
            id="sub-pro",
            plan_key=PlanKey.INDIVIDUAL_PRO,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.ANNUAL,
            add_ons=[AddOnGrant(type=AddOnType.STORAGE_100_GB, quantity=2)],
        )
    )

    subject = EntitlementSubject(user_id="user-3")
    result = entitlement_service.get_entitlements(subject, subscription_id="sub-pro")

    assert result.payload.storage_quota_gb == 300


def test_cache_invalidation_refreshes_entitlements(entitlement_service, repositories):
    subscription_repo, _ = repositories
    subscription_repo.add(
        SubscriptionRecord(
            id="sub-pro",
            plan_key=PlanKey.INDIVIDUAL_PRO,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
        )
    )
    subject = EntitlementSubject(user_id="user-4")

    first = entitlement_service.get_entitlements(subject, subscription_id="sub-pro")
    assert first.payload.storage_quota_gb == 100

    subscription_repo.add(
        SubscriptionRecord(
            id="sub-pro",
            plan_key=PlanKey.INDIVIDUAL_PRO,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
            add_ons=[AddOnGrant(type=AddOnType.STORAGE_100_GB, quantity=1)],
        )
    )

    cached = entitlement_service.get_entitlements(subject, subscription_id="sub-pro")
    assert cached.payload.storage_quota_gb == 100

    entitlement_service.invalidate_subscription("sub-pro")
    refreshed = entitlement_service.get_entitlements(subject, subscription_id="sub-pro")
    assert refreshed.payload.storage_quota_gb == 200


def test_missing_membership_raises(entitlement_service, repositories):
    subscription_repo, _ = repositories
    subscription_repo.add(
        SubscriptionRecord(
            id="sub-team",
            plan_key=PlanKey.TEAM,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
        )
    )

    subject = EntitlementSubject(user_id="user-unknown", organization_id="org-absent")

    with pytest.raises(LookupError):
        entitlement_service.get_entitlements(subject, subscription_id="sub-team")