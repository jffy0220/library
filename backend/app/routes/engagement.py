"""API routes for engagement features."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..schemas.engagement import EngagementStatus
from ..services import engagement as engagement_service
from .notifications import _get_current_user

router = APIRouter(prefix="/api/engagement", tags=["engagement"])


@router.get("/status", response_model=EngagementStatus)
def get_engagement_status(
    *,
    timezone: Optional[str] = Query(
        default=None, description="Preferred timezone for calculations"
    ),
    current_user=Depends(_get_current_user),
) -> EngagementStatus:
    """Return current engagement metrics for the authenticated user."""

    payload = engagement_service.engagement_status(
        current_user.id,
        timezone_name=timezone,
    )
    return EngagementStatus.model_validate(payload)


__all__ = ["router", "get_engagement_status"]