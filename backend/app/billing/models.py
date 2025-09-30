"""Domain models for the billing system."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..entitlements.models import BillingInterval, PlanKey, SubscriptionStatus


class BillingCustomerType(str, Enum):
    """Supported customer entity types."""

    USER = "user"
    ORGANIZATION = "organization"


class PurchaseIntentStatus(str, Enum):
    """Lifecycle status for a checkout purchase intent."""

    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELED = "canceled"


class BillingWebhookEventType(str, Enum):
    """Webhook event types that the application reacts to."""

    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELED = "subscription.canceled"
    INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
    INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"


class InvoiceStatus(str, Enum):
    """Status of a persisted invoice record."""

    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"
    PAST_DUE = "past_due"


class SeatReconciliationOutcome(str, Enum):
    """Possible results of a seat reconciliation attempt."""

    IN_SYNC = "in_sync"
    UPDATED = "updated"
    OVERAGE_REQUIRES_ACTION = "overage_requires_action"
    UNDER_UTILIZED = "under_utilized"


class PurchaseIntent(BaseModel):
    """Represents a pending checkout session awaiting confirmation."""

    intent_id: str = Field(description="Public identifier shared with the billing provider")
    customer_type: BillingCustomerType
    customer_id: str = Field(description="Identifier for the purchasing user or organization")
    plan_key: PlanKey
    billing_interval: BillingInterval
    seat_quantity: int = Field(default=1, ge=1)
    status: PurchaseIntentStatus = PurchaseIntentStatus.PENDING
    provider_session_id: Optional[str] = None
    provider_session_url: Optional[str] = None
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class Subscription(BaseModel):
    """Normalized subscription state synchronized from the billing provider."""

    subscription_id: str
    provider_id: str
    customer_type: BillingCustomerType
    customer_id: str
    plan_key: PlanKey
    billing_interval: BillingInterval
    status: SubscriptionStatus
    seat_quantity: int = Field(default=1, ge=1)
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    cancel_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    grace_period_expires_at: Optional[datetime] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @property
    def is_past_due(self) -> bool:
        """Return ``True`` when the subscription is in a past-due state."""
        return self.status == SubscriptionStatus.PAST_DUE


class InvoiceRecord(BaseModel):
    """Persistent invoice details exposed to end users."""

    invoice_id: str
    subscription_id: str
    amount_due: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: InvoiceStatus
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    provider_invoice_id: Optional[str] = None
    pdf_url: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()


class BillingWebhookEvent(BaseModel):
    """Normalized webhook payload stored for idempotency tracking."""

    event_id: str
    event_type: BillingWebhookEventType
    payload: Dict[str, object]
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class BillingAuditEventType(str, Enum):
    """Audit event categories emitted by the billing subsystem."""

    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_RECOVERED = "payment_recovered"
    GRACE_PERIOD_EXPIRED = "grace_period_expired"


class BillingAuditEvent(BaseModel):
    """Structured audit event for analytics and notifications."""

    event_type: BillingAuditEventType
    subscription_id: Optional[str] = None
    actor_id: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class PaymentFailure(BaseModel):
    """Represents a payment failure that triggered a grace period."""

    subscription_id: str
    invoice_id: Optional[str] = None
    amount_due: int = 0
    currency: str = "USD"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    grace_period_expires_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class CheckoutSession(BaseModel):
    """Return value of a checkout session creation request."""

    intent: PurchaseIntent
    checkout_url: str
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class SeatReconciliationResult(BaseModel):
    """Outcome of a seat reconciliation attempt."""

    subscription_id: str
    member_count: int
    seat_quantity: int
    outcome: SeatReconciliationOutcome
    updated_subscription: Optional[Subscription] = None

    model_config = ConfigDict(populate_by_name=True, frozen=True)