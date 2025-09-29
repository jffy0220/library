"""Schema definitions for engagement features."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StreakBadge(BaseModel):
    name: str
    icon: str
    threshold: int
    description: str

    model_config = ConfigDict(populate_by_name=True)


class StreakStatus(BaseModel):
    current: int
    longest: int
    active_today: bool = Field(alias="activeToday")
    last_active_date: Optional[date] = Field(default=None, alias="lastActiveDate")
    timezone: str
    current_badge: Optional[StreakBadge] = Field(default=None, alias="currentBadge")
    next_badge: Optional[StreakBadge] = Field(default=None, alias="nextBadge")

    model_config = ConfigDict(populate_by_name=True)


class EngagementStatus(BaseModel):
    streak: StreakStatus
    show_capture_prompt: bool = Field(alias="showCapturePrompt")
    timezone: str

    model_config = ConfigDict(populate_by_name=True)


__all__ = ["StreakBadge", "StreakStatus", "EngagementStatus"]