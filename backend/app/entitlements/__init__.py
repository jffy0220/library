"""Entitlements domain models and services."""

from .catalog import PLAN_CATALOG, ADD_ON_CATALOG, get_plan_definition, get_add_on_definition
from .cache import EntitlementCache, InMemoryEntitlementCache
from .models import (
    AddOnGrant,
    AddOnType,
    BillingInterval,
    EntitlementPayload,
    EntitlementResult,
    EntitlementSubject,
    FeatureBundle,
    MembershipRole,
    OrganizationMembership,
    PlanKey,
    SubscriptionRecord,
    SubscriptionStatus,
)
from .service import (
    EntitlementService,
    HMACTokenSigner,
    MembershipRepository,
    SubscriptionRepository,
    TokenSigner,
)

__all__ = [
    "PLAN_CATALOG",
    "ADD_ON_CATALOG",
    "get_plan_definition",
    "get_add_on_definition",
    "EntitlementCache",
    "InMemoryEntitlementCache",
    "AddOnGrant",
    "AddOnType",
    "BillingInterval",
    "EntitlementPayload",
    "EntitlementResult",
    "EntitlementSubject",
    "FeatureBundle",
    "MembershipRole",
    "OrganizationMembership",
    "PlanKey",
    "SubscriptionRecord",
    "SubscriptionStatus",
    "EntitlementService",
    "HMACTokenSigner",
    "MembershipRepository",
    "SubscriptionRepository",
    "TokenSigner",
]