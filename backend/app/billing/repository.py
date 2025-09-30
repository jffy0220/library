"""Persistence layer for billing domain objects."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import cursor as PgCursor

from .models import (
    BillingCustomerType,
    BillingWebhookEvent,
    InvoiceRecord,
    InvoiceStatus,
    PurchaseIntent,
    PurchaseIntentStatus,
    SeatReconciliationResult,
    Subscription,
)
from ..entitlements.models import BillingInterval, PlanKey, SubscriptionStatus

try:  # pragma: no cover - resolve connection helper when imported from FastAPI app
    from backend.app_context import get_conn
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name != "backend":
        raise
    from ...app_context import get_conn  # type: ignore[no-redef]


@contextmanager
def managed_connection(conn: Optional[PgConnection] = None):
    """Context manager that manages transaction boundaries for optional connections."""

    if conn is not None:
        yield conn, False
        return

    connection = get_conn()
    try:
        yield connection, True
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _row_to_purchase_intent(row: dict) -> PurchaseIntent:
    return PurchaseIntent(
        intent_id=row["intent_id"],
        customer_type=BillingCustomerType(row["customer_type"]),
        customer_id=row["customer_id"],
        plan_key=PlanKey(row["plan_key"]),
        billing_interval=BillingInterval(row["billing_interval"]),
        seat_quantity=int(row["seat_quantity"]),
        status=PurchaseIntentStatus(row["status"]),
        provider_session_id=row.get("provider_session_id"),
        provider_session_url=row.get("provider_session_url"),
        return_url=row.get("return_url"),
        cancel_url=row.get("cancel_url"),
        metadata=row.get("metadata") or {},
        expires_at=row.get("expires_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_subscription(row: dict) -> Subscription:
    return Subscription(
        subscription_id=row["subscription_id"],
        provider_id=row["provider_id"],
        customer_type=BillingCustomerType(row["customer_type"]),
        customer_id=row["customer_id"],
        plan_key=PlanKey(row["plan_key"]),
        billing_interval=BillingInterval(row["billing_interval"]),
        status=SubscriptionStatus(row["status"]),
        seat_quantity=int(row["seat_quantity"]),
        current_period_start=row.get("current_period_start"),
        current_period_end=row.get("current_period_end"),
        trial_end=row.get("trial_end"),
        cancel_at=row.get("cancel_at"),
        canceled_at=row.get("canceled_at"),
        grace_period_expires_at=row.get("grace_period_expires_at"),
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_invoice(row: dict) -> InvoiceRecord:
    return InvoiceRecord(
        invoice_id=row["invoice_id"],
        subscription_id=row["subscription_id"],
        amount_due=int(row["amount_due"]),
        currency=row["currency"],
        status=InvoiceStatus(row["status"]),
        period_start=row.get("period_start"),
        period_end=row.get("period_end"),
        provider_invoice_id=row.get("provider_invoice_id"),
        pdf_url=row.get("pdf_url"),
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresBillingRepository:
    """Concrete repository persisting billing models in PostgreSQL."""

    def __init__(self, *, conn: Optional[PgConnection] = None) -> None:
        self._conn = conn

    @contextmanager
    def _cursor(self) -> Iterable[PgCursor]:
        with managed_connection(self._conn) as (connection, managed):
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                yield cursor
                if managed:
                    connection.commit()
            except Exception:
                if managed:
                    connection.rollback()
                raise
            finally:
                cursor.close()

    def save_purchase_intent(self, intent: PurchaseIntent) -> PurchaseIntent:
        """Insert or update a purchase intent record."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO billing_purchase_intents (
                    intent_id,
                    customer_type,
                    customer_id,
                    plan_key,
                    billing_interval,
                    seat_quantity,
                    status,
                    provider_session_id,
                    provider_session_url,
                    return_url,
                    cancel_url,
                    metadata,
                    expires_at
                )
                VALUES (%(intent_id)s, %(customer_type)s, %(customer_id)s, %(plan_key)s,
                        %(billing_interval)s, %(seat_quantity)s, %(status)s,
                        %(provider_session_id)s, %(provider_session_url)s,
                        %(return_url)s, %(cancel_url)s, %(metadata)s, %(expires_at)s)
                ON CONFLICT (intent_id) DO UPDATE SET
                    seat_quantity = EXCLUDED.seat_quantity,
                    status = EXCLUDED.status,
                    provider_session_id = EXCLUDED.provider_session_id,
                    provider_session_url = EXCLUDED.provider_session_url,
                    return_url = EXCLUDED.return_url,
                    cancel_url = EXCLUDED.cancel_url,
                    metadata = EXCLUDED.metadata,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                RETURNING *
                """,
                {
                    "intent_id": intent.intent_id,
                    "customer_type": intent.customer_type.value,
                    "customer_id": intent.customer_id,
                    "plan_key": intent.plan_key.value,
                    "billing_interval": intent.billing_interval.value,
                    "seat_quantity": intent.seat_quantity,
                    "status": intent.status.value,
                    "provider_session_id": intent.provider_session_id,
                    "provider_session_url": intent.provider_session_url,
                    "return_url": intent.return_url,
                    "cancel_url": intent.cancel_url,
                    "metadata": psycopg2.extras.Json(intent.metadata),
                    "expires_at": intent.expires_at,
                },
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Failed to persist purchase intent")
            return _row_to_purchase_intent(row)

    def get_purchase_intent(self, intent_id: str) -> Optional[PurchaseIntent]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM billing_purchase_intents
                WHERE intent_id = %s
                LIMIT 1
                """,
                (intent_id,),
            )
            row = cursor.fetchone()
            return _row_to_purchase_intent(row) if row else None

    def get_purchase_intent_by_session(self, session_id: str) -> Optional[PurchaseIntent]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM billing_purchase_intents
                WHERE provider_session_id = %s
                LIMIT 1
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            return _row_to_purchase_intent(row) if row else None

    def upsert_subscription(self, subscription: Subscription) -> Subscription:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO billing_subscriptions (
                    subscription_id,
                    provider_id,
                    customer_type,
                    customer_id,
                    plan_key,
                    billing_interval,
                    status,
                    seat_quantity,
                    current_period_start,
                    current_period_end,
                    trial_end,
                    cancel_at,
                    canceled_at,
                    grace_period_expires_at,
                    metadata
                )
                VALUES (%(subscription_id)s, %(provider_id)s, %(customer_type)s, %(customer_id)s,
                        %(plan_key)s, %(billing_interval)s, %(status)s, %(seat_quantity)s,
                        %(current_period_start)s, %(current_period_end)s, %(trial_end)s,
                        %(cancel_at)s, %(canceled_at)s, %(grace_period_expires_at)s,
                        %(metadata)s)
                ON CONFLICT (subscription_id) DO UPDATE SET
                    provider_id = EXCLUDED.provider_id,
                    customer_type = EXCLUDED.customer_type,
                    customer_id = EXCLUDED.customer_id,
                    plan_key = EXCLUDED.plan_key,
                    billing_interval = EXCLUDED.billing_interval,
                    status = EXCLUDED.status,
                    seat_quantity = EXCLUDED.seat_quantity,
                    current_period_start = EXCLUDED.current_period_start,
                    current_period_end = EXCLUDED.current_period_end,
                    trial_end = EXCLUDED.trial_end,
                    cancel_at = EXCLUDED.cancel_at,
                    canceled_at = EXCLUDED.canceled_at,
                    grace_period_expires_at = EXCLUDED.grace_period_expires_at,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                {
                    "subscription_id": subscription.subscription_id,
                    "provider_id": subscription.provider_id,
                    "customer_type": subscription.customer_type.value,
                    "customer_id": subscription.customer_id,
                    "plan_key": subscription.plan_key.value,
                    "billing_interval": subscription.billing_interval.value,
                    "status": subscription.status.value,
                    "seat_quantity": subscription.seat_quantity,
                    "current_period_start": subscription.current_period_start,
                    "current_period_end": subscription.current_period_end,
                    "trial_end": subscription.trial_end,
                    "cancel_at": subscription.cancel_at,
                    "canceled_at": subscription.canceled_at,
                    "grace_period_expires_at": subscription.grace_period_expires_at,
                    "metadata": psycopg2.extras.Json(subscription.metadata),
                },
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Failed to persist subscription")
            return _row_to_subscription(row)

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM billing_subscriptions
                WHERE subscription_id = %s
                LIMIT 1
                """,
                (subscription_id,),
            )
            row = cursor.fetchone()
            return _row_to_subscription(row) if row else None

    def record_invoice(self, invoice: InvoiceRecord) -> InvoiceRecord:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO billing_invoices (
                    invoice_id,
                    subscription_id,
                    amount_due,
                    currency,
                    status,
                    period_start,
                    period_end,
                    provider_invoice_id,
                    pdf_url,
                    metadata
                )
                VALUES (%(invoice_id)s, %(subscription_id)s, %(amount_due)s, %(currency)s,
                        %(status)s, %(period_start)s, %(period_end)s, %(provider_invoice_id)s,
                        %(pdf_url)s, %(metadata)s)
                ON CONFLICT (invoice_id) DO UPDATE SET
                    amount_due = EXCLUDED.amount_due,
                    currency = EXCLUDED.currency,
                    status = EXCLUDED.status,
                    period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    provider_invoice_id = EXCLUDED.provider_invoice_id,
                    pdf_url = EXCLUDED.pdf_url,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                {
                    "invoice_id": invoice.invoice_id,
                    "subscription_id": invoice.subscription_id,
                    "amount_due": invoice.amount_due,
                    "currency": invoice.currency,
                    "status": invoice.status.value,
                    "period_start": invoice.period_start,
                    "period_end": invoice.period_end,
                    "provider_invoice_id": invoice.provider_invoice_id,
                    "pdf_url": invoice.pdf_url,
                    "metadata": psycopg2.extras.Json(invoice.metadata),
                },
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Failed to persist invoice")
            return _row_to_invoice(row)

    def list_invoices(self, *, customer_type: BillingCustomerType, customer_id: str, limit: int = 20) -> list[InvoiceRecord]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT inv.*
                FROM billing_invoices AS inv
                JOIN billing_subscriptions AS sub ON sub.subscription_id = inv.subscription_id
                WHERE sub.customer_type = %s AND sub.customer_id = %s
                ORDER BY inv.created_at DESC
                LIMIT %s
                """,
                (customer_type.value, customer_id, limit),
            )
            rows = cursor.fetchall() or []
            return [_row_to_invoice(row) for row in rows]

    def record_webhook_event(self, event: BillingWebhookEvent) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO billing_webhook_events (
                    event_id,
                    event_type,
                    payload,
                    received_at,
                    processed_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    event.event_type.value,
                    psycopg2.extras.Json(event.payload),
                    event.received_at,
                ),
            )
            return cursor.rowcount > 0

    def mark_purchase_intent_completed(self, intent_id: str) -> Optional[PurchaseIntent]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE billing_purchase_intents
                SET status = %s, updated_at = NOW()
                WHERE intent_id = %s
                RETURNING *
                """,
                (PurchaseIntentStatus.COMPLETED.value, intent_id),
            )
            row = cursor.fetchone()
            return _row_to_purchase_intent(row) if row else None

    def update_subscription_status(
        self,
        subscription_id: str,
        *,
        status: SubscriptionStatus,
        grace_period_expires_at: Optional[datetime],
    ) -> Optional[Subscription]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE billing_subscriptions
                SET status = %s,
                    grace_period_expires_at = %s,
                    updated_at = NOW()
                WHERE subscription_id = %s
                RETURNING *
                """,
                (status.value, grace_period_expires_at, subscription_id),
            )
            row = cursor.fetchone()
            return _row_to_subscription(row) if row else None

    def record_seat_reconciliation(
        self,
        result: SeatReconciliationResult,
    ) -> SeatReconciliationResult:
        # Placeholder hook for future persistence of reconciliation history.
        return result


__all__ = ["PostgresBillingRepository"]