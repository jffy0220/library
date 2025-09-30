"""API routes exposing billing functionality."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status

from ..billing import BillingCustomerType, BillingWebhookEvent, BillingWebhookEventType
from ..schemas.billing import (
    BillingWebhookPayload,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    InvoiceListResponse,
    PortalSessionRequest,
    PortalSessionResponse,
    SeatReconciliationRequest,
    SeatReconciliationResponse,
)
from ..services.billing import get_billing_service


def _resolve_get_current_user() -> Callable[..., Any]:  # pragma: no cover
    try:
        from backend.main import get_current_user as resolved
    except ModuleNotFoundError as exc:
        if exc.name != "backend":
            raise
        from ...main import get_current_user as resolved  # type: ignore[no-redef]
    return resolved


@lru_cache(maxsize=1)
def _get_current_user_callable() -> Callable[..., Any]:
    return _resolve_get_current_user()


_SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")


def _get_current_user(
    session_token: Optional[str] = Cookie(None, alias=_SESSION_COOKIE_NAME),
):
    resolved = _get_current_user_callable()
    return resolved(session_token=session_token)


router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    payload: CheckoutSessionRequest,
    *,
    current_user=Depends(_get_current_user),
) -> CheckoutSessionResponse:
    service = get_billing_service()
    user_id = str(current_user.id)
    if (
        payload.customer_type == BillingCustomerType.USER
        and payload.customer_id != user_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create checkout session for another user")

    try:
        session = service.create_checkout_session(
            customer_type=payload.customer_type,
            customer_id=payload.customer_id,
            plan_key=payload.plan_key,
            billing_interval=payload.billing_interval,
            seat_quantity=payload.seat_quantity,
            return_url=payload.return_url,
            cancel_url=payload.cancel_url,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CheckoutSessionResponse.from_checkout(session)


@router.post("/portal-session", response_model=PortalSessionResponse)
def create_portal_session(
    payload: PortalSessionRequest,
    *,
    current_user=Depends(_get_current_user),
) -> PortalSessionResponse:
    service = get_billing_service()
    user_id = str(current_user.id)
    if payload.customer_type == BillingCustomerType.USER and payload.customer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create portal session for another user")

    session = service.create_portal_session(
        customer_type=payload.customer_type,
        customer_id=payload.customer_id,
        return_url=payload.return_url,
    )
    return PortalSessionResponse(url=session.get("url", ""), expires_at=session.get("expires_at"))


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def receive_webhook(payload: BillingWebhookPayload) -> Response:
    service = get_billing_service()
    try:
        event = BillingWebhookEvent(
            event_id=payload.id,
            event_type=BillingWebhookEventType(payload.type),
            payload=payload.payload,
            received_at=payload.received_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service.handle_webhook(event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(
    customer_type: BillingCustomerType = Query(alias="customerType"),
    customer_id: str = Query(alias="customerId"),
    *,
    current_user=Depends(_get_current_user),
) -> InvoiceListResponse:
    if customer_type == BillingCustomerType.USER and customer_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view invoices for another user")

    service = get_billing_service()
    invoices = service.list_invoices(customer_type=customer_type, customer_id=customer_id)
    return InvoiceListResponse(invoices=list(invoices))


@router.post("/subscriptions/{subscription_id}/reconcile-seats", response_model=SeatReconciliationResponse)
def reconcile_seats(
    subscription_id: str,
    payload: SeatReconciliationRequest,
    *,
    current_user=Depends(_get_current_user),
) -> SeatReconciliationResponse:
    service = get_billing_service()
    try:
        result = service.reconcile_seats(subscription_id, member_count=payload.member_count)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SeatReconciliationResponse.from_result(result)