"""Application wiring for the billing service."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Dict
from uuid import uuid4

from ..billing import (
    BillingAuditEvent,
    BillingCustomerType,
    BillingEventLogger,
    BillingNotifier,
    BillingService,
    EntitlementInvalidator,
    PaymentFailure,
    PaymentProvider,
)
from ..billing.repository import PostgresBillingRepository


logger = logging.getLogger("billing")


class LoggingBillingNotifier(BillingNotifier):
    """Notifier that records billing notifications to the application logger."""

    def notify_payment_failure(self, failure: PaymentFailure) -> None:
        logger.warning(
            "Payment failure for subscription %s invoice=%s amount=%s %s",
            failure.subscription_id,
            failure.invoice_id,
            failure.amount_due,
            failure.currency,
        )

    def notify_grace_period_expired(self, subscription) -> None:
        logger.warning(
            "Grace period expired for subscription %s customer=%s",
            subscription.subscription_id,
            subscription.customer_id,
        )

    def notify_seat_overage(self, subscription, member_count: int) -> None:
        logger.warning(
            "Seat overage detected subscription=%s seats=%s members=%s",
            subscription.subscription_id,
            subscription.seat_quantity,
            member_count,
        )


class LoggingBillingEventLogger(BillingEventLogger):
    """Simple event logger forwarding billing audit events to logging."""

    def log(self, event: BillingAuditEvent) -> None:
        logger.info(
            "Billing event %s subscription=%s actor=%s metadata=%s",
            event.event_type.value,
            event.subscription_id,
            event.actor_id,
            event.metadata,
        )


class LoggingEntitlementInvalidator(EntitlementInvalidator):
    """Placeholder invalidator that emits log statements until cache hooks exist."""

    def invalidate_subscription(self, subscription_id: str) -> None:
        logger.debug("Invalidate subscription entitlements %s", subscription_id)

    def invalidate_user(self, user_id: str) -> None:
        logger.debug("Invalidate user entitlements %s", user_id)

    def invalidate_organization(self, organization_id: str) -> None:
        logger.debug("Invalidate organization entitlements %s", organization_id)


class LocalSandboxPaymentProvider(PaymentProvider):
    """Minimal provider implementation for local development and tests."""

    def create_checkout_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        plan_key,
        billing_interval,
        seat_quantity: int,
        metadata: Dict[str, str],
        return_url: str,
        cancel_url: str,
    ) -> Dict[str, object]:
        session_id = f"cs_{uuid4().hex}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        url = f"https://billing.local/checkout/{session_id}"
        return {
            "id": session_id,
            "url": url,
            "expires_at": expires_at,
            "metadata": metadata,
            "return_url": return_url,
            "cancel_url": cancel_url,
        }

    def create_billing_portal_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, object]:
        session_id = f"ps_{uuid4().hex}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        url = f"https://billing.local/portal/{customer_type.value}/{customer_id}"
        return {"id": session_id, "url": url, "expires_at": expires_at, "return_url": return_url}

    def update_subscription_seats(self, provider_subscription_id: str, seat_quantity: int):
        raise NotImplementedError("Seat updates require real billing provider integration")


@lru_cache(maxsize=1)
def get_billing_service() -> BillingService:
    repository = PostgresBillingRepository()
    provider = LocalSandboxPaymentProvider()
    notifier = LoggingBillingNotifier()
    event_logger = LoggingBillingEventLogger()
    entitlement_invalidator = LoggingEntitlementInvalidator()
    service = BillingService(
        repository=repository,
        provider=provider,
        notifier=notifier,
        event_logger=event_logger,
        entitlement_invalidator=entitlement_invalidator,
    )
    return service


__all__ = ["get_billing_service", "LoggingBillingNotifier", "LoggingBillingEventLogger"]