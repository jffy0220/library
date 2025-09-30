"""Core service coordinating billing flows with external providers."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Protocol, Sequence
from uuid import uuid4

from ..entitlements.models import BillingInterval, PlanKey, SubscriptionStatus
from .models import (
    BillingAuditEvent,
    BillingAuditEventType,
    BillingCustomerType,
    BillingWebhookEvent,
    BillingWebhookEventType,
    CheckoutSession,
    InvoiceRecord,
    InvoiceStatus,
    PaymentFailure,
    PurchaseIntent,
    PurchaseIntentStatus,
    SeatReconciliationOutcome,
    SeatReconciliationResult,
    Subscription,
)


class PaymentProvider(Protocol):
    """External payment processor integration."""

    def create_checkout_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        plan_key: PlanKey,
        billing_interval: BillingInterval,
        seat_quantity: int,
        metadata: Dict[str, str],
        return_url: str,
        cancel_url: str,
    ) -> Dict[str, object]:
        """Create a provider checkout session."""

    def create_billing_portal_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, object]:
        """Create a provider managed billing portal session."""

    def update_subscription_seats(self, provider_subscription_id: str, seat_quantity: int) -> Subscription:
        """Update seat quantity for a subscription."""


class BillingNotifier(Protocol):
    """Dispatches billing related notifications to end users."""

    def notify_payment_failure(self, failure: PaymentFailure) -> None:
        ...

    def notify_grace_period_expired(self, subscription: Subscription) -> None:
        ...

    def notify_seat_overage(self, subscription: Subscription, member_count: int) -> None:
        ...


class BillingEventLogger(Protocol):
    """Captures structured billing audit events."""

    def log(self, event: BillingAuditEvent) -> None:
        ...


class EntitlementInvalidator(Protocol):
    """Invalidates entitlement caches affected by billing changes."""

    def invalidate_subscription(self, subscription_id: str) -> None:
        ...

    def invalidate_user(self, user_id: str) -> None:
        ...

    def invalidate_organization(self, organization_id: str) -> None:
        ...


class BillingRepository(Protocol):
    """Persistence operations required by the billing service."""

    def save_purchase_intent(self, intent: PurchaseIntent) -> PurchaseIntent:
        ...

    def get_purchase_intent(self, intent_id: str) -> Optional[PurchaseIntent]:
        ...

    def get_purchase_intent_by_session(self, session_id: str) -> Optional[PurchaseIntent]:
        ...

    def mark_purchase_intent_completed(self, intent_id: str) -> Optional[PurchaseIntent]:
        ...

    def upsert_subscription(self, subscription: Subscription) -> Subscription:
        ...

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        ...

    def update_subscription_status(
        self,
        subscription_id: str,
        *,
        status: SubscriptionStatus,
        grace_period_expires_at: Optional[datetime],
    ) -> Optional[Subscription]:
        ...

    def record_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        ...

    def list_invoices(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        limit: int = 20,
    ) -> Sequence[InvoiceRecord]:
        ...

    def record_webhook_event(self, event: BillingWebhookEvent) -> bool:
        ...

    def record_seat_reconciliation(self, result: SeatReconciliationResult) -> SeatReconciliationResult:
        ...


# ``slots`` support for ``dataclass`` was added in Python 3.10. The backend
# can run under Python 3.9 in some environments (e.g., local development), so
# we enable slots conditionally to maintain compatibility while preserving the
# optimization where available.
_dataclass_kwargs = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_dataclass_kwargs)
class BillingService:
    """Coordinates purchase intents, subscriptions, and notifications."""

    repository: BillingRepository
    provider: PaymentProvider
    notifier: BillingNotifier
    event_logger: BillingEventLogger
    entitlement_invalidator: EntitlementInvalidator
    grace_period_days: int = 7

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_checkout_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        plan_key: PlanKey,
        billing_interval: BillingInterval,
        seat_quantity: int,
        return_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> CheckoutSession:
        if seat_quantity < 1:
            raise ValueError("seat_quantity must be >= 1")

        intent = PurchaseIntent(
            intent_id=f"pi_{uuid4().hex}",
            customer_type=customer_type,
            customer_id=customer_id,
            plan_key=plan_key,
            billing_interval=billing_interval,
            seat_quantity=seat_quantity,
            return_url=return_url,
            cancel_url=cancel_url,
            metadata=metadata or {},
            status=PurchaseIntentStatus.PENDING,
            created_at=self._now(),
            updated_at=self._now(),
        )
        stored_intent = self.repository.save_purchase_intent(intent)

        provider_session = self.provider.create_checkout_session(
            customer_type=customer_type,
            customer_id=customer_id,
            plan_key=plan_key,
            billing_interval=billing_interval,
            seat_quantity=seat_quantity,
            metadata={"purchase_intent_id": stored_intent.intent_id, **stored_intent.metadata},
            return_url=return_url,
            cancel_url=cancel_url,
        )

        updated_intent = stored_intent.model_copy(
            update={
                "provider_session_id": provider_session.get("id"),
                "provider_session_url": provider_session.get("url"),
                "expires_at": provider_session.get("expires_at"),
                "metadata": provider_session.get("metadata", stored_intent.metadata),
                "updated_at": self._now(),
            }
        )
        persisted = self.repository.save_purchase_intent(updated_intent)
        return CheckoutSession(intent=persisted, checkout_url=persisted.provider_session_url or "", expires_at=persisted.expires_at)

    def create_portal_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, object]:
        session = self.provider.create_billing_portal_session(
            customer_type=customer_type,
            customer_id=customer_id,
            return_url=return_url,
        )
        return session

    def mark_intent_completed(self, provider_session_id: str) -> Subscription:
        intent = self.repository.get_purchase_intent_by_session(provider_session_id)
        if intent is None:
            raise LookupError("Unknown checkout session")

        updated_intent = self.repository.mark_purchase_intent_completed(intent.intent_id)
        if updated_intent is None:
            raise RuntimeError("Failed to mark purchase intent as completed")

        subscription_id = updated_intent.metadata.get("subscription_id")
        if not subscription_id:
            raise KeyError("subscription_id missing from purchase intent metadata")

        subscription = self.repository.get_subscription(subscription_id)
        if subscription is None:
            raise LookupError("Subscription not found for purchase intent")

        self._invalidate_entitlements(subscription)
        self.event_logger.log(
            BillingAuditEvent(
                event_type=BillingAuditEventType.SUBSCRIPTION_ACTIVATED,
                subscription_id=subscription.subscription_id,
                actor_id=subscription.customer_id,
            )
        )
        return subscription

    def handle_webhook(self, event: BillingWebhookEvent) -> None:
        stored = self.repository.record_webhook_event(event)
        if not stored:
            return

        if event.event_type in {
            BillingWebhookEventType.SUBSCRIPTION_CREATED,
            BillingWebhookEventType.SUBSCRIPTION_UPDATED,
            BillingWebhookEventType.SUBSCRIPTION_CANCELED,
        }:
            self._handle_subscription_event(event)
        elif event.event_type == BillingWebhookEventType.INVOICE_PAYMENT_FAILED:
            self._handle_payment_failed(event)
        elif event.event_type == BillingWebhookEventType.INVOICE_PAYMENT_SUCCEEDED:
            self._handle_payment_succeeded(event)

    def list_invoices(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        limit: int = 20,
    ) -> Sequence[InvoiceRecord]:
        return self.repository.list_invoices(
            customer_type=customer_type, customer_id=customer_id, limit=limit
        )

    def reconcile_seats(
        self,
        subscription_id: str,
        *,
        member_count: int,
    ) -> SeatReconciliationResult:
        subscription = self.repository.get_subscription(subscription_id)
        if subscription is None:
            raise LookupError("Subscription not found")

        if member_count < 0:
            raise ValueError("member_count must be >= 0")

        if member_count == subscription.seat_quantity:
            result = SeatReconciliationResult(
                subscription_id=subscription.subscription_id,
                member_count=member_count,
                seat_quantity=subscription.seat_quantity,
                outcome=SeatReconciliationOutcome.IN_SYNC,
            )
            return self.repository.record_seat_reconciliation(result)

        if member_count > subscription.seat_quantity:
            try:
                updated_subscription = self.provider.update_subscription_seats(
                    subscription.provider_id, member_count
                )
                persisted = self.repository.upsert_subscription(updated_subscription)
                self._invalidate_entitlements(persisted)
                result = SeatReconciliationResult(
                    subscription_id=persisted.subscription_id,
                    member_count=member_count,
                    seat_quantity=persisted.seat_quantity,
                    outcome=SeatReconciliationOutcome.UPDATED,
                    updated_subscription=persisted,
                )
                return self.repository.record_seat_reconciliation(result)
            except Exception:
                self.notifier.notify_seat_overage(subscription, member_count)
                result = SeatReconciliationResult(
                    subscription_id=subscription.subscription_id,
                    member_count=member_count,
                    seat_quantity=subscription.seat_quantity,
                    outcome=SeatReconciliationOutcome.OVERAGE_REQUIRES_ACTION,
                )
                return self.repository.record_seat_reconciliation(result)

        # Seats exceed members
        result = SeatReconciliationResult(
            subscription_id=subscription.subscription_id,
            member_count=member_count,
            seat_quantity=subscription.seat_quantity,
            outcome=SeatReconciliationOutcome.UNDER_UTILIZED,
        )
        return self.repository.record_seat_reconciliation(result)

    def process_grace_period_expiration(self, subscription_id: str) -> Subscription:
        subscription = self.repository.get_subscription(subscription_id)
        if subscription is None:
            raise LookupError("Subscription not found")

        updated = self.repository.update_subscription_status(
            subscription_id,
            status=SubscriptionStatus.CANCELED,
            grace_period_expires_at=None,
        )
        if updated is None:
            raise RuntimeError("Failed to update subscription status")

        self.notifier.notify_grace_period_expired(updated)
        self.event_logger.log(
            BillingAuditEvent(
                event_type=BillingAuditEventType.GRACE_PERIOD_EXPIRED,
                subscription_id=updated.subscription_id,
                actor_id=updated.customer_id,
            )
        )
        self._invalidate_entitlements(updated)
        return updated

    def _handle_subscription_event(self, event: BillingWebhookEvent) -> None:
        payload = event.payload.get("subscription")
        if not isinstance(payload, dict):
            raise ValueError("subscription payload missing from webhook event")

        subscription = self._subscription_from_payload(payload)
        persisted = self.repository.upsert_subscription(subscription)

        if event.event_type == BillingWebhookEventType.SUBSCRIPTION_CANCELED:
            audit_type = BillingAuditEventType.SUBSCRIPTION_CANCELED
        elif persisted.status == SubscriptionStatus.ACTIVE:
            audit_type = BillingAuditEventType.SUBSCRIPTION_ACTIVATED
        else:
            audit_type = BillingAuditEventType.SUBSCRIPTION_UPDATED

        self.event_logger.log(
            BillingAuditEvent(
                event_type=audit_type,
                subscription_id=persisted.subscription_id,
                actor_id=persisted.customer_id,
            )
        )
        self._invalidate_entitlements(persisted)

    def _handle_payment_failed(self, event: BillingWebhookEvent) -> None:
        payload = event.payload.get("invoice")
        if not isinstance(payload, dict):
            raise ValueError("invoice payload missing from webhook")

        invoice = self._invoice_from_payload(payload)
        persisted_invoice = self.repository.record_invoice(invoice)
        grace_period_expires_at = self._now() + timedelta(days=self.grace_period_days)
        subscription = self.repository.update_subscription_status(
            invoice.subscription_id,
            status=SubscriptionStatus.PAST_DUE,
            grace_period_expires_at=grace_period_expires_at,
        )
        if subscription is None:
            raise LookupError("Subscription not found for invoice")

        failure = PaymentFailure(
            subscription_id=invoice.subscription_id,
            invoice_id=persisted_invoice.invoice_id,
            amount_due=persisted_invoice.amount_due,
            currency=persisted_invoice.currency,
            occurred_at=self._now(),
            grace_period_expires_at=grace_period_expires_at,
        )
        self.notifier.notify_payment_failure(failure)
        self.event_logger.log(
            BillingAuditEvent(
                event_type=BillingAuditEventType.PAYMENT_FAILED,
                subscription_id=invoice.subscription_id,
                actor_id=subscription.customer_id,
                metadata={"invoice_id": persisted_invoice.invoice_id},
            )
        )
        self._invalidate_entitlements(subscription)

    def _handle_payment_succeeded(self, event: BillingWebhookEvent) -> None:
        payload = event.payload.get("invoice")
        if not isinstance(payload, dict):
            raise ValueError("invoice payload missing from webhook")

        invoice = self._invoice_from_payload(payload)
        persisted_invoice = self.repository.record_invoice(invoice)
        subscription = self.repository.update_subscription_status(
            invoice.subscription_id,
            status=SubscriptionStatus.ACTIVE,
            grace_period_expires_at=None,
        )
        if subscription is None:
            raise LookupError("Subscription not found for invoice")

        self.event_logger.log(
            BillingAuditEvent(
                event_type=BillingAuditEventType.PAYMENT_RECOVERED,
                subscription_id=invoice.subscription_id,
                actor_id=subscription.customer_id,
                metadata={"invoice_id": persisted_invoice.invoice_id},
            )
        )
        self._invalidate_entitlements(subscription)

    def _subscription_from_payload(self, payload: Dict[str, object]) -> Subscription:
        try:
            plan_key = PlanKey(str(payload["plan_key"]))
        except Exception as exc:  # pragma: no cover - defensive path
            raise ValueError("Invalid plan_key in subscription payload") from exc

        interval = BillingInterval(str(payload.get("billing_interval", BillingInterval.MONTHLY.value)))
        status = SubscriptionStatus(str(payload.get("status", SubscriptionStatus.ACTIVE.value)))
        customer_type = BillingCustomerType(str(payload.get("customer_type", BillingCustomerType.USER.value)))

        subscription = Subscription(
            subscription_id=str(payload["subscription_id"]),
            provider_id=str(payload.get("provider_id", payload["subscription_id"])),
            customer_type=customer_type,
            customer_id=str(payload.get("customer_id", "")),
            plan_key=plan_key,
            billing_interval=interval,
            status=status,
            seat_quantity=int(payload.get("seat_quantity", 1)),
            current_period_start=_parse_optional_datetime(payload.get("current_period_start")),
            current_period_end=_parse_optional_datetime(payload.get("current_period_end")),
            trial_end=_parse_optional_datetime(payload.get("trial_end")),
            cancel_at=_parse_optional_datetime(payload.get("cancel_at")),
            canceled_at=_parse_optional_datetime(payload.get("canceled_at")),
            grace_period_expires_at=_parse_optional_datetime(payload.get("grace_period_expires_at")),
            metadata=_safe_metadata(payload.get("metadata")),
            created_at=_parse_optional_datetime(payload.get("created_at")) or self._now(),
            updated_at=_parse_optional_datetime(payload.get("updated_at")) or self._now(),
        )
        return subscription

    def _invoice_from_payload(self, payload: Dict[str, object]) -> InvoiceRecord:
        subscription_id = str(payload.get("subscription_id"))
        if not subscription_id:
            raise ValueError("subscription_id missing from invoice payload")

        status = InvoiceStatus(str(payload.get("status", InvoiceStatus.OPEN.value)))
        invoice = InvoiceRecord(
            invoice_id=str(payload.get("invoice_id", f"in_{uuid4().hex}")),
            subscription_id=subscription_id,
            amount_due=int(payload.get("amount_due", 0)),
            currency=str(payload.get("currency", "USD")),
            status=status,
            period_start=_parse_optional_datetime(payload.get("period_start")),
            period_end=_parse_optional_datetime(payload.get("period_end")),
            provider_invoice_id=payload.get("provider_invoice_id") and str(payload.get("provider_invoice_id")),
            pdf_url=payload.get("pdf_url") and str(payload.get("pdf_url")),
            metadata=_safe_metadata(payload.get("metadata")),
            created_at=_parse_optional_datetime(payload.get("created_at")) or self._now(),
            updated_at=_parse_optional_datetime(payload.get("updated_at")) or self._now(),
        )
        return invoice

    def _invalidate_entitlements(self, subscription: Subscription) -> None:
        self.entitlement_invalidator.invalidate_subscription(subscription.subscription_id)
        if subscription.customer_type == BillingCustomerType.USER:
            self.entitlement_invalidator.invalidate_user(subscription.customer_id)
        else:
            self.entitlement_invalidator.invalidate_organization(subscription.customer_id)


def _parse_optional_datetime(value: object) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError("Unsupported datetime value")


def _safe_metadata(value: object) -> Dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {}


__all__ = [
    "BillingEventLogger",
    "BillingNotifier",
    "BillingRepository",
    "BillingService",
    "EntitlementInvalidator",
    "PaymentProvider",
]