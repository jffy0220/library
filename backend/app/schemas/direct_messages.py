from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DirectMessageParticipant(BaseModel):
    user_id: int = Field(alias="userId")
    username: str

    model_config = ConfigDict(populate_by_name=True)


class DirectMessagePreview(BaseModel):
    id: int
    thread_id: int = Field(alias="threadId")
    sender_id: int = Field(alias="senderId")
    sender_username: str = Field(alias="senderUsername")
    body: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageThread(BaseModel):
    id: int
    created_at: datetime = Field(alias="createdAt")
    last_message_at: Optional[datetime] = Field(default=None, alias="lastMessageAt")
    participant: DirectMessageParticipant
    last_message: Optional[DirectMessagePreview] = Field(default=None, alias="lastMessage")
    unread_count: int = Field(default=0, alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageThreadList(BaseModel):
    threads: List[DirectMessageThread]

    model_config = ConfigDict(populate_by_name=True)


class DirectMessage(BaseModel):
    id: int
    thread_id: int = Field(alias="threadId")
    sender_id: int = Field(alias="senderId")
    sender_username: str = Field(alias="senderUsername")
    body: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageList(BaseModel):
    messages: List[DirectMessage]
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")
    has_more: bool = Field(default=False, alias="hasMore")

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageStartRequest(BaseModel):
    username: str


class DirectMessageStartResponse(BaseModel):
    thread_id: int = Field(alias="threadId")
    thread: DirectMessageThread

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageSendRequest(BaseModel):
    body: str


class DirectMessageSendResponse(BaseModel):
    message: DirectMessage
    thread: DirectMessageThread

    model_config = ConfigDict(populate_by_name=True)


class DirectMessageMarkReadResponse(BaseModel):
    unread_count: int = Field(alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)