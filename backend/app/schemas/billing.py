"""API schemas for billing endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..billing import (
    BillingCustomerType,
    CheckoutSession,
    InvoiceRecord,
    PurchaseIntent,
    SeatReconciliationResult,
)
from ..entitlements.models import BillingInterval, PlanKey


class CheckoutSessionRequest(BaseModel):
    plan_key: PlanKey = Field(alias="planKey")
    billing_interval: BillingInterval = Field(alias="billingInterval")
    seat_quantity: int = Field(alias="seatQuantity", ge=1)
    return_url: str = Field(alias="returnUrl")
    cancel_url: str = Field(alias="cancelUrl")
    metadata: Dict[str, str] = Field(default_factory=dict)
    customer_type: BillingCustomerType = Field(alias="customerType")
    customer_id: str = Field(alias="customerId")

    model_config = ConfigDict(populate_by_name=True)


class CheckoutSessionResponse(BaseModel):
    intent: PurchaseIntent
    checkout_url: str = Field(alias="checkoutUrl")
    expires_at: Optional[datetime] = Field(alias="expiresAt", default=None)

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_checkout(cls, session: CheckoutSession) -> "CheckoutSessionResponse":
        return cls(
            intent=session.intent,
            checkout_url=session.checkout_url,
            expires_at=session.expires_at,
        )


class PortalSessionRequest(BaseModel):
    customer_type: BillingCustomerType = Field(alias="customerType")
    customer_id: str = Field(alias="customerId")
    return_url: str = Field(alias="returnUrl")

    model_config = ConfigDict(populate_by_name=True)


class PortalSessionResponse(BaseModel):
    url: str
    expires_at: Optional[datetime] = Field(alias="expiresAt", default=None)

    model_config = ConfigDict(populate_by_name=True)


class BillingWebhookPayload(BaseModel):
    id: str
    type: str
    payload: Dict[str, object]
    received_at: datetime = Field(alias="receivedAt")

    model_config = ConfigDict(populate_by_name=True)


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceRecord]

    model_config = ConfigDict(populate_by_name=True)


class SeatReconciliationResponse(BaseModel):
    result: SeatReconciliationResult

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_result(cls, result: SeatReconciliationResult) -> "SeatReconciliationResponse":
        return cls(result=result)


class SeatReconciliationRequest(BaseModel):
    member_count: int = Field(alias="memberCount", ge=0)

    model_config = ConfigDict(populate_by_name=True)