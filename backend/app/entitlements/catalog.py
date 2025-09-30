"""Static catalog definitions for plans and add-ons."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .models import (
    AddOnType,
    BillingInterval,
    FeatureBundle,
    MembershipRole,
    PlanKey,
)


@dataclass(frozen=True)
class PlanDefinition:
    """Describes a subscription plan and its entitlement mapping."""

    key: PlanKey
    display_name: str
    billing_intervals: Tuple[BillingInterval, ...]
    member_bundle: FeatureBundle
    admin_override: Optional[FeatureBundle] = None
    supports_add_ons: Tuple[AddOnType, ...] = ()
    per_seat: bool = False

    def bundle_for_role(self, role: Optional[MembershipRole]) -> FeatureBundle:
        bundle = self.member_bundle
        if role in {MembershipRole.ADMIN, MembershipRole.OWNER} and self.admin_override:
            return bundle.merge(self.admin_override)
        return bundle


@dataclass(frozen=True)
class AddOnDefinition:
    """Describes an add-on and how it impacts entitlements."""

    add_on_type: AddOnType
    storage_increment_gb: int = 0


FREE_BUNDLE = FeatureBundle(
    ads_disabled=False,
    sync_enabled=False,
    search_advanced=False,
    storage_quota_gb=5,
)

INDIVIDUAL_PRO_BUNDLE = FeatureBundle(
    ads_disabled=True,
    sync_enabled=True,
    search_advanced=True,
    storage_quota_gb=100,
)

TEAM_MEMBER_BUNDLE = FeatureBundle(
    ads_disabled=True,
    sync_enabled=True,
    search_advanced=True,
    storage_quota_gb=100,
)

TEAM_ADMIN_OVERRIDE = FeatureBundle(org_admin=True)

PLAN_CATALOG: Dict[PlanKey, PlanDefinition] = {
    PlanKey.FREE: PlanDefinition(
        key=PlanKey.FREE,
        display_name="Free",
        billing_intervals=(BillingInterval.MONTHLY,),
        member_bundle=FREE_BUNDLE,
    ),
    PlanKey.INDIVIDUAL_PRO: PlanDefinition(
        key=PlanKey.INDIVIDUAL_PRO,
        display_name="Individual (Pro)",
        billing_intervals=(BillingInterval.MONTHLY, BillingInterval.ANNUAL),
        member_bundle=INDIVIDUAL_PRO_BUNDLE,
        supports_add_ons=(AddOnType.STORAGE_100_GB,),
    ),
    PlanKey.TEAM: PlanDefinition(
        key=PlanKey.TEAM,
        display_name="Teams",
        billing_intervals=(BillingInterval.MONTHLY, BillingInterval.ANNUAL),
        member_bundle=TEAM_MEMBER_BUNDLE,
        admin_override=TEAM_ADMIN_OVERRIDE,
        supports_add_ons=(AddOnType.STORAGE_100_GB,),
        per_seat=True,
    ),
}

ADD_ON_CATALOG: Dict[AddOnType, AddOnDefinition] = {
    AddOnType.STORAGE_100_GB: AddOnDefinition(
        add_on_type=AddOnType.STORAGE_100_GB,
        storage_increment_gb=100,
    ),
}


def get_plan_definition(plan_key: PlanKey) -> PlanDefinition:
    """Return a plan definition, raising if unsupported."""

    try:
        return PLAN_CATALOG[plan_key]
    except KeyError as exc:  # pragma: no cover - guarded by static catalog
        raise KeyError(f"Unknown plan key: {plan_key}") from exc


def get_add_on_definition(add_on_type: AddOnType) -> AddOnDefinition:
    """Return an add-on definition, raising if unsupported."""

    try:
        return ADD_ON_CATALOG[add_on_type]
    except KeyError as exc:  # pragma: no cover - guarded by static catalog
        raise KeyError(f"Unknown add-on type: {add_on_type}") from exc