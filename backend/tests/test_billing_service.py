"""Unit tests for the billing service groundwork."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Sequence

import pytest

from backend.app.billing import (
    BillingAuditEvent,
    BillingAuditEventType,
    BillingCustomerType,
    BillingService,
    BillingWebhookEvent,
    BillingWebhookEventType,
    InvoiceRecord,
    InvoiceStatus,
    PaymentFailure,
    PurchaseIntent,
    PurchaseIntentStatus,
    SeatReconciliationOutcome,
    SeatReconciliationResult,
    Subscription,
)
from backend.app.billing.service import BillingEventLogger, BillingNotifier, BillingRepository, EntitlementInvalidator, PaymentProvider
from backend.app.entitlements.models import BillingInterval, PlanKey, SubscriptionStatus


class InMemoryBillingRepository(BillingRepository):
    def __init__(self) -> None:
        self.purchase_intents: Dict[str, PurchaseIntent] = {}
        self.session_index: Dict[str, str] = {}
        self.subscriptions: Dict[str, Subscription] = {}
        self.invoices: Dict[str, InvoiceRecord] = {}
        self.webhook_events: set[str] = set()
        self.reconciliation_results: list[SeatReconciliationResult] = []

    def save_purchase_intent(self, intent: PurchaseIntent) -> PurchaseIntent:
        self.purchase_intents[intent.intent_id] = intent
        if intent.provider_session_id:
            self.session_index[intent.provider_session_id] = intent.intent_id
        return intent

    def get_purchase_intent(self, intent_id: str) -> Optional[PurchaseIntent]:
        return self.purchase_intents.get(intent_id)

    def get_purchase_intent_by_session(self, session_id: str) -> Optional[PurchaseIntent]:
        intent_id = self.session_index.get(session_id)
        return self.purchase_intents.get(intent_id) if intent_id else None

    def mark_purchase_intent_completed(self, intent_id: str) -> Optional[PurchaseIntent]:
        intent = self.purchase_intents.get(intent_id)
        if intent is None:
            return None
        updated = intent.model_copy(update={"status": PurchaseIntentStatus.COMPLETED})
        self.save_purchase_intent(updated)
        return updated

    def upsert_subscription(self, subscription: Subscription) -> Subscription:
        self.subscriptions[subscription.subscription_id] = subscription
        return subscription

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        return self.subscriptions.get(subscription_id)

    def update_subscription_status(
        self,
        subscription_id: str,
        *,
        status: SubscriptionStatus,
        grace_period_expires_at: Optional[datetime],
    ) -> Optional[Subscription]:
        subscription = self.subscriptions.get(subscription_id)
        if subscription is None:
            return None
        updated = subscription.model_copy(
            update={
                "status": status,
                "grace_period_expires_at": grace_period_expires_at,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.subscriptions[subscription_id] = updated
        return updated

    def record_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        self.invoices[invoice.invoice_id] = invoice
        return invoice

    def list_invoices(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        limit: int = 20,
    ) -> Sequence[InvoiceRecord]:
        matching = [
            invoice
            for invoice in sorted(
                self.invoices.values(),
                key=lambda inv: inv.created_at,
                reverse=True,
            )
            if (subscription := self.subscriptions.get(invoice.subscription_id))
            and subscription.customer_type == customer_type
            and subscription.customer_id == customer_id
        ]
        return matching[:limit]

    def record_webhook_event(self, event: BillingWebhookEvent) -> bool:
        if event.event_id in self.webhook_events:
            return False
        self.webhook_events.add(event.event_id)
        return True

    def record_seat_reconciliation(self, result: SeatReconciliationResult) -> SeatReconciliationResult:
        self.reconciliation_results.append(result)
        return result


class FakePaymentProvider(PaymentProvider):
    def __init__(self) -> None:
        self.checkout_sessions: list[Dict[str, object]] = []
        self.portal_sessions: list[Dict[str, object]] = []
        self.updated_seats: list[tuple[str, int]] = []
        self.subscription_templates: Dict[str, Subscription] = {}
        self.extra_metadata: Dict[str, str] = {"subscription_id": "sub_fake"}

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
        session_id = f"cs_{len(self.checkout_sessions) + 1}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        payload = {
            "id": session_id,
            "url": f"https://provider.test/checkout/{session_id}",
            "expires_at": expires_at,
            "metadata": {**metadata, **self.extra_metadata},
        }
        self.checkout_sessions.append(payload)
        return payload

    def create_billing_portal_session(
        self,
        *,
        customer_type: BillingCustomerType,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, object]:
        session_id = f"ps_{len(self.portal_sessions) + 1}"
        payload = {
            "id": session_id,
            "url": f"https://provider.test/portal/{customer_type.value}/{customer_id}",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "return_url": return_url,
        }
        self.portal_sessions.append(payload)
        return payload

    def update_subscription_seats(self, provider_subscription_id: str, seat_quantity: int) -> Subscription:
        template = self.subscription_templates.get(provider_subscription_id)
        if template is None:
            raise LookupError("subscription not registered in provider")
        updated = template.model_copy(update={"seat_quantity": seat_quantity, "updated_at": datetime.now(timezone.utc)})
        self.subscription_templates[provider_subscription_id] = updated
        self.updated_seats.append((provider_subscription_id, seat_quantity))
        return updated


class FakeNotifier(BillingNotifier):
    def __init__(self) -> None:
        self.payment_failures: list[PaymentFailure] = []
        self.grace_expired: list[Subscription] = []
        self.seat_overages: list[tuple[Subscription, int]] = []

    def notify_payment_failure(self, failure: PaymentFailure) -> None:
        self.payment_failures.append(failure)

    def notify_grace_period_expired(self, subscription: Subscription) -> None:
        self.grace_expired.append(subscription)

    def notify_seat_overage(self, subscription: Subscription, member_count: int) -> None:
        self.seat_overages.append((subscription, member_count))


class FakeEventLogger(BillingEventLogger):
    def __init__(self) -> None:
        self.events: list[BillingAuditEvent] = []

    def log(self, event: BillingAuditEvent) -> None:
        self.events.append(event)


class FakeInvalidator(EntitlementInvalidator):
    def __init__(self) -> None:
        self.subscription_ids: list[str] = []
        self.user_ids: list[str] = []
        self.organization_ids: list[str] = []

    def invalidate_subscription(self, subscription_id: str) -> None:
        self.subscription_ids.append(subscription_id)

    def invalidate_user(self, user_id: str) -> None:
        self.user_ids.append(user_id)

    def invalidate_organization(self, organization_id: str) -> None:
        self.organization_ids.append(organization_id)


@pytest.fixture
def billing_components():
    repository = InMemoryBillingRepository()
    provider = FakePaymentProvider()
    notifier = FakeNotifier()
    event_logger = FakeEventLogger()
    invalidator = FakeInvalidator()
    service = BillingService(
        repository=repository,
        provider=provider,
        notifier=notifier,
        event_logger=event_logger,
        entitlement_invalidator=invalidator,
        grace_period_days=3,
    )
    return repository, provider, notifier, event_logger, invalidator, service


def test_create_checkout_session_persists_intent(billing_components):
    repository, provider, _, _, _, service = billing_components
    session = service.create_checkout_session(
        customer_type=BillingCustomerType.USER,
        customer_id="user-1",
        plan_key=PlanKey.INDIVIDUAL_PRO,
        billing_interval=BillingInterval.MONTHLY,
        seat_quantity=1,
        return_url="https://app.test/return",
        cancel_url="https://app.test/cancel",
        metadata={"source": "test"},
    )

    stored_intent = repository.get_purchase_intent(session.intent.intent_id)
    assert stored_intent is not None
    assert stored_intent.provider_session_id == provider.checkout_sessions[0]["id"]
    assert "purchase_intent_id" in provider.checkout_sessions[0]["metadata"]
    assert session.intent.status == PurchaseIntentStatus.PENDING


def test_handle_subscription_webhook_updates_records(billing_components):
    repository, _, _, event_logger, invalidator, service = billing_components
    event = BillingWebhookEvent(
        event_id="evt_sub_1",
        event_type=BillingWebhookEventType.SUBSCRIPTION_UPDATED,
        payload={
            "subscription": {
                "subscription_id": "sub_1",
                "provider_id": "psub_1",
                "customer_type": BillingCustomerType.USER.value,
                "customer_id": "user-1",
                "plan_key": PlanKey.INDIVIDUAL_PRO.value,
                "billing_interval": BillingInterval.ANNUAL.value,
                "status": SubscriptionStatus.ACTIVE.value,
                "seat_quantity": 3,
            }
        },
        received_at=datetime.now(timezone.utc),
    )

    service.handle_webhook(event)

    stored = repository.get_subscription("sub_1")
    assert stored is not None
    assert stored.plan_key == PlanKey.INDIVIDUAL_PRO
    assert stored.seat_quantity == 3
    assert event_logger.events[-1].event_type == BillingAuditEventType.SUBSCRIPTION_ACTIVATED
    assert "sub_1" in invalidator.subscription_ids
    assert "user-1" in invalidator.user_ids


def test_payment_failure_marks_subscription_past_due(billing_components):
    repository, _, notifier, event_logger, _, service = billing_components
    subscription = Subscription(
        subscription_id="sub_fail",
        provider_id="psub_fail",
        customer_type=BillingCustomerType.USER,
        customer_id="user-42",
        plan_key=PlanKey.INDIVIDUAL_PRO,
        billing_interval=BillingInterval.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        seat_quantity=1,
    )
    repository.upsert_subscription(subscription)

    event = BillingWebhookEvent(
        event_id="evt_invoice_fail",
        event_type=BillingWebhookEventType.INVOICE_PAYMENT_FAILED,
        payload={
            "invoice": {
                "invoice_id": "in_1",
                "subscription_id": "sub_fail",
                "amount_due": 2500,
                "currency": "usd",
                "status": InvoiceStatus.OPEN.value,
            }
        },
        received_at=datetime.now(timezone.utc),
    )

    service.handle_webhook(event)

    updated = repository.get_subscription("sub_fail")
    assert updated is not None
    assert updated.status == SubscriptionStatus.PAST_DUE
    assert notifier.payment_failures[0].subscription_id == "sub_fail"
    assert event_logger.events[-1].event_type == BillingAuditEventType.PAYMENT_FAILED


def test_webhook_idempotency_prevents_duplicate_processing(billing_components):
    repository, _, _, event_logger, _, service = billing_components
    repository.upsert_subscription(
        Subscription(
            subscription_id="sub_dup",
            provider_id="psub_dup",
            customer_type=BillingCustomerType.USER,
            customer_id="user-dup",
            plan_key=PlanKey.INDIVIDUAL_PRO,
            billing_interval=BillingInterval.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            seat_quantity=1,
        )
    )
    event = BillingWebhookEvent(
        event_id="evt_dup",
        event_type=BillingWebhookEventType.SUBSCRIPTION_UPDATED,
        payload={
            "subscription": {
                "subscription_id": "sub_dup",
                "provider_id": "psub_dup",
                "customer_type": BillingCustomerType.USER.value,
                "customer_id": "user-dup",
                "plan_key": PlanKey.INDIVIDUAL_PRO.value,
                "billing_interval": BillingInterval.MONTHLY.value,
                "status": SubscriptionStatus.ACTIVE.value,
                "seat_quantity": 2,
            }
        },
        received_at=datetime.now(timezone.utc),
    )

    service.handle_webhook(event)
    service.handle_webhook(event)

    assert len(event_logger.events) == 1
    assert repository.get_subscription("sub_dup").seat_quantity == 2


def test_reconcile_seats_updates_provider_when_under_provisioned(billing_components):
    repository, provider, notifier, _, invalidator, service = billing_components
    subscription = Subscription(
        subscription_id="sub_team",
        provider_id="psub_team",
        customer_type=BillingCustomerType.ORGANIZATION,
        customer_id="org-1",
        plan_key=PlanKey.TEAM,
        billing_interval=BillingInterval.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        seat_quantity=3,
    )
    repository.upsert_subscription(subscription)
    provider.subscription_templates["psub_team"] = subscription

    result = service.reconcile_seats("sub_team", member_count=5)

    assert result.outcome == SeatReconciliationOutcome.UPDATED
    assert repository.get_subscription("sub_team").seat_quantity == 5
    assert invalidator.organization_ids == ["org-1"]
    assert notifier.seat_overages == []


def test_reconcile_seats_notifies_on_provider_failure(billing_components):
    repository, provider, notifier, _, _, service = billing_components
    subscription = Subscription(
        subscription_id="sub_org",
        provider_id="psub_org",
        customer_type=BillingCustomerType.ORGANIZATION,
        customer_id="org-5",
        plan_key=PlanKey.TEAM,
        billing_interval=BillingInterval.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        seat_quantity=2,
    )
    repository.upsert_subscription(subscription)
    # Intentionally do not register subscription with provider to force failure.

    result = service.reconcile_seats("sub_org", member_count=4)

    assert result.outcome == SeatReconciliationOutcome.OVERAGE_REQUIRES_ACTION
    assert notifier.seat_overages[0][0].subscription_id == "sub_org"


def test_process_grace_period_expiration_logs_and_notifies(billing_components):
    repository, _, notifier, event_logger, invalidator, service = billing_components
    subscription = Subscription(
        subscription_id="sub_grace",
        provider_id="psub_grace",
        customer_type=BillingCustomerType.USER,
        customer_id="user-grace",
        plan_key=PlanKey.INDIVIDUAL_PRO,
        billing_interval=BillingInterval.MONTHLY,
        status=SubscriptionStatus.PAST_DUE,
        seat_quantity=1,
        grace_period_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    repository.upsert_subscription(subscription)

    updated = service.process_grace_period_expiration("sub_grace")

    assert updated.status == SubscriptionStatus.CANCELED
    assert notifier.grace_expired[0].subscription_id == "sub_grace"
    assert event_logger.events[-1].event_type == BillingAuditEventType.GRACE_PERIOD_EXPIRED
    assert invalidator.user_ids[-1] == "user-grace"