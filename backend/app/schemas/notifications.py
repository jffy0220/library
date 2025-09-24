from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    REPLY_TO_SNIPPET = "reply_to_snippet"
    REPLY_TO_COMMENT = "reply_to_comment"
    MENTION = "mention"
    VOTE_ON_YOUR_SNIPPET = "vote_on_your_snippet"
    MODERATION_UPDATE = "moderation_update"
    SYSTEM = "system"


class EmailDigestOption(str, Enum):
    OFF = "off"
    DAILY = "daily"
    WEEKLY = "weekly"


class NotificationCreate(BaseModel):
    user_id: int = Field(alias="userId")
    type: NotificationType
    actor_user_id: Optional[int] = Field(default=None, alias="actorUserId")
    snippet_id: Optional[int] = Field(default=None, alias="snippetId")
    comment_id: Optional[int] = Field(default=None, alias="commentId")
    title: Optional[str] = None
    body: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class Notification(BaseModel):
    id: int
    user_id: int = Field(alias="userId")
    type: NotificationType
    actor_user_id: Optional[int] = Field(default=None, alias="actorUserId")
    snippet_id: Optional[int] = Field(default=None, alias="snippetId")
    comment_id: Optional[int] = Field(default=None, alias="commentId")
    title: Optional[str] = None
    body: Optional[str] = None
    is_read: bool = Field(alias="isRead")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class NotificationListResponse(BaseModel):
    items: List[Notification]
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")

    model_config = ConfigDict(populate_by_name=True)


class NotificationMarkReadRequest(BaseModel):
    ids: List[int] = Field(min_length=1, validation_alias=AliasChoices("ids", "notificationIds"))

    model_config = ConfigDict(populate_by_name=True)


class NotificationMarkReadResponse(BaseModel):
    updated_ids: List[int] = Field(default_factory=list, alias="updatedIds")
    unread_count: int = Field(alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)


class NotificationUnreadCount(BaseModel):
    count: int


class NotificationPreferences(BaseModel):
    user_id: int = Field(alias="userId")
    reply_to_snippet: bool = Field(default=True, alias="replyToSnippet")
    reply_to_comment: bool = Field(default=True, alias="replyToComment")
    mention: bool = Field(default=True)
    vote_on_your_snippet: bool = Field(default=True, alias="voteOnYourSnippet")
    moderation_update: bool = Field(default=True, alias="moderationUpdate")
    system: bool = Field(default=True)
    email_digest: EmailDigestOption = Field(default=EmailDigestOption.WEEKLY, alias="emailDigest")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def default(cls, user_id: int) -> "NotificationPreferences":
        return cls(userId=user_id)


class NotificationPreferencesUpdate(BaseModel):
    reply_to_snippet: Optional[bool] = Field(default=None, alias="replyToSnippet")
    reply_to_comment: Optional[bool] = Field(default=None, alias="replyToComment")
    mention: Optional[bool] = None
    vote_on_your_snippet: Optional[bool] = Field(default=None, alias="voteOnYourSnippet")
    moderation_update: Optional[bool] = Field(default=None, alias="moderationUpdate")
    system: Optional[bool] = None
    email_digest: Optional[EmailDigestOption] = Field(default=None, alias="emailDigest")

    model_config = ConfigDict(populate_by_name=True)