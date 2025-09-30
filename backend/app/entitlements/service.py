"""Service responsible for computing and caching entitlement payloads."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional, Protocol, Sequence

from .cache import EntitlementCache
from .catalog import get_add_on_definition, get_plan_definition
from .models import (
    AddOnGrant,
    AddOnType,
    EntitlementPayload,
    EntitlementResult,
    EntitlementSubject,
    FeatureBundle,
    MembershipRole,
    OrganizationMembership,
    PlanKey,
    SubscriptionRecord,
)


class SubscriptionRepository(Protocol):
    """Data access layer for subscription records."""

    def get_subscription(self, subscription_id: str) -> Optional[SubscriptionRecord]:
        ...


class MembershipRepository(Protocol):
    """Data access layer for organization memberships."""

    def get_membership(self, user_id: str, organization_id: str) -> Optional[OrganizationMembership]:
        ...


class TokenSigner(Protocol):
    """Protocol describing token signing behavior."""

    def sign(self, claims: Mapping[str, object]) -> str:
        ...


class HMACTokenSigner:
    """Simple HMAC based token signer for entitlement payloads."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("secret must be provided")
        self._secret = secret.encode("utf-8")

    def sign(self, claims: Mapping[str, object]) -> str:
        serialized = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hmac.new(self._secret, serialized, hashlib.sha256).digest()
        token_bytes = base64.urlsafe_b64encode(serialized + b"." + digest)
        return token_bytes.decode("utf-8")


class EntitlementService:
    """Coordinates plan resolution, entitlement computation, and caching."""

    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        membership_repository: MembershipRepository,
        cache: EntitlementCache,
        token_signer: TokenSigner,
        *,
        clock: Optional[Callable[[], datetime]] = None,
        ttl_seconds: int = 300,
    ) -> None:
        self._subscription_repository = subscription_repository
        self._membership_repository = membership_repository
        self._cache = cache
        self._token_signer = token_signer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ttl_seconds = max(ttl_seconds, 60)

    def get_entitlements(
        self,
        subject: EntitlementSubject,
        subscription_id: Optional[str],
    ) -> EntitlementResult:
        """Return entitlements for the given subject."""

        cache_key = subject.cache_key(subscription_id)
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        subscription = self._resolve_subscription(subscription_id)
        role: Optional[MembershipRole] = None
        if subject.organization_id:
            membership = self._membership_repository.get_membership(
                subject.user_id, subject.organization_id
            )
            if not membership:
                raise LookupError(
                    f"No membership found for user={subject.user_id} in"
                    f" organization={subject.organization_id}"
                )
            role = membership.role

        payload = self._compute_payload(subject, subscription, role)
        expires_at = self._clock() + timedelta(seconds=self._ttl_seconds)
        claims = payload.to_claims(expires_at)
        token = self._token_signer.sign(claims)
        result = EntitlementResult(payload=payload, token=token, expires_at=expires_at)
        self._cache.set(cache_key, result, expires_at, subject.tags(subscription_id))
        return result

    def invalidate_user(self, user_id: str) -> None:
        self._cache.invalidate({f"user:{user_id}"})

    def invalidate_subscription(self, subscription_id: str) -> None:
        self._cache.invalidate({f"subscription:{subscription_id}"})

    def invalidate_organization(self, organization_id: str) -> None:
        self._cache.invalidate({f"organization:{organization_id}"})

    def _resolve_subscription(self, subscription_id: Optional[str]) -> Optional[SubscriptionRecord]:
        if not subscription_id:
            return None
        subscription = self._subscription_repository.get_subscription(subscription_id)
        if subscription and not subscription.is_active:
            return None
        return subscription

    def _compute_payload(
        self,
        subject: EntitlementSubject,
        subscription: Optional[SubscriptionRecord],
        role: Optional[MembershipRole],
    ) -> EntitlementPayload:
        if subscription is None:
            plan_key = PlanKey.FREE
            add_ons: tuple[AddOnGrant, ...] = tuple()
        else:
            plan_key = subscription.plan_key
            add_ons = tuple(subscription.add_ons)

        plan_definition = get_plan_definition(plan_key)
        bundle = plan_definition.bundle_for_role(role)

        if add_ons:
            bundle = self._apply_add_ons(bundle, plan_definition.supports_add_ons, add_ons)

        payload = EntitlementPayload(
            plan=plan_definition.key,
            feature_flags=bundle.to_flags(),
            subscription_id=subscription.id if subscription else None,
            organization_id=subject.organization_id,
            role=role,
        )
        return payload

    def _apply_add_ons(
        self,
        bundle: FeatureBundle,
        supported_add_ons: Sequence[AddOnType],
        add_ons: tuple[AddOnGrant, ...],
    ) -> FeatureBundle:
        if not supported_add_ons:
            return bundle

        supported_types = set(supported_add_ons)
        total_storage_increment = 0
        for grant in add_ons:
            if grant.add_on_type not in supported_types:
                continue
            add_on_definition = get_add_on_definition(grant.add_on_type)
            total_storage_increment += add_on_definition.storage_increment_gb * grant.quantity

        if total_storage_increment:
            bundle = bundle.with_added_storage(total_storage_increment)

        return bundle