"""Domain models for entitlements and plan computation."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanKey(str, Enum):
    """Canonical identifiers for subscription plans."""

    FREE = "free"
    INDIVIDUAL_PRO = "individual_pro"
    TEAM = "team"


class BillingInterval(str, Enum):
    """Supported billing frequencies."""

    MONTHLY = "monthly"
    ANNUAL = "annual"


class AddOnType(str, Enum):
    """Enumerates supported add-on products."""

    STORAGE_100_GB = "storage_100_gb"


@dataclass(frozen=True)
class FeatureBundle:
    """Represents a normalized set of entitlement feature flags."""

    ads_disabled: bool = False
    sync_enabled: bool = False
    search_advanced: bool = False
    storage_quota_gb: int = 5
    org_admin: bool = False

    def merge(self, override: "FeatureBundle") -> "FeatureBundle":
        """Merge another bundle into this one, preferring override values."""

        if override is self:
            return self
        data = {field.name: getattr(self, field.name) for field in fields(self)}
        default_bundle = FeatureBundle()
        for field in fields(self):
            override_value = getattr(override, field.name)
            default_value = getattr(default_bundle, field.name)
            if override_value != default_value:
                data[field.name] = override_value
        return FeatureBundle(**data)

    def with_added_storage(self, increment_gb: int) -> "FeatureBundle":
        """Return a new bundle with increased storage."""

        return replace(self, storage_quota_gb=self.storage_quota_gb + increment_gb)

    def to_flags(self) -> Dict[str, int | bool]:
        """Serialize bundle to flattened flag keys."""

        return {
            "ads.disabled": self.ads_disabled,
            "sync.enabled": self.sync_enabled,
            "search.advanced": self.search_advanced,
            "storage.quota_gb": self.storage_quota_gb,
            "org.admin": self.org_admin,
        }


class AddOnGrant(BaseModel):
    """Represents a provisioned add-on tied to a subscription."""

    add_on_type: AddOnType = Field(alias="type")
    quantity: int = 1

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, value: int) -> int:
        if value < 1:
            raise ValueError("quantity must be >= 1")
        return value


class SubscriptionStatus(str, Enum):
    """Lifecycle state for subscriptions."""

    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"


class SubscriptionRecord(BaseModel):
    """Normalized subscription payload used for entitlement computation."""

    id: str
    plan_key: PlanKey
    status: SubscriptionStatus
    billing_interval: BillingInterval
    add_ons: Sequence[AddOnGrant] = Field(default_factory=tuple)

    model_config = ConfigDict(frozen=True)

    @property
    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE


class MembershipRole(str, Enum):
    """Roles a member can have within an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class OrganizationMembership(BaseModel):
    """Represents a user's association with an organization subscription."""

    organization_id: str
    user_id: str
    role: MembershipRole = MembershipRole.MEMBER
    seat_consumed: bool = True

    model_config = ConfigDict(frozen=True)


class EntitlementSubject(BaseModel):
    """Represents the subject for which entitlements are requested."""

    user_id: str
    organization_id: Optional[str] = None

    model_config = ConfigDict(frozen=True)

    def cache_key(self, subscription_id: Optional[str]) -> str:
        org_component = self.organization_id or "self"
        subscription_component = subscription_id or "none"
        return f"user:{self.user_id}|org:{org_component}|sub:{subscription_component}"

    def tags(self, subscription_id: Optional[str]) -> Set[str]:
        tags: Set[str] = {f"user:{self.user_id}"}
        if self.organization_id:
            tags.add(f"organization:{self.organization_id}")
        if subscription_id:
            tags.add(f"subscription:{subscription_id}")
        return tags


class EntitlementPayload(BaseModel):
    """Computed entitlement payload returned to clients."""

    plan: PlanKey
    feature_flags: Dict[str, int | bool]
    subscription_id: Optional[str]
    organization_id: Optional[str] = None
    role: Optional[MembershipRole] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(frozen=True)

    @property
    def storage_quota_gb(self) -> int:
        return int(self.feature_flags.get("storage.quota_gb", 0))

    def to_claims(self, expires_at: datetime) -> Dict[str, object]:
        """Represent the payload as token claims."""

        claims: Dict[str, object] = {
            "plan": self.plan.value,
            "feature_flags": self.feature_flags,
            "generated_at": self.generated_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        if self.organization_id:
            claims["organization_id"] = self.organization_id
        if self.role:
            claims["role"] = self.role.value
        if self.subscription_id:
            claims["subscription_id"] = self.subscription_id
        return claims


class EntitlementResult(BaseModel):
    """Wrapper containing the entitlement payload and signed token."""

    payload: EntitlementPayload
    token: str
    expires_at: datetime

    model_config = ConfigDict(frozen=True)