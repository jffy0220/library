from functools import lru_cache
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas.direct_messages import (
    DirectMessageList,
    DirectMessageMarkReadResponse,
    DirectMessageSendRequest,
    DirectMessageSendResponse,
    DirectMessageStartRequest,
    DirectMessageStartResponse,
    DirectMessageThreadList,
)


def _resolve_get_current_user() -> Callable[..., Any]:  # pragma: no cover - helper for lazy import
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


def _get_current_user(*args: Any, **kwargs: Any):
    return _get_current_user_callable()(*args, **kwargs)


router = APIRouter(prefix="/api/dm", tags=["direct-messages"])


@router.post("/start", response_model=DirectMessageStartResponse)
def start_conversation(
    payload: DirectMessageStartRequest,
    *,
    current_user=Depends(_get_current_user),
) -> DirectMessageStartResponse:
    from ..services import direct_messages as dm_service

    try:
        thread = dm_service.start_thread(
            initiator_id=current_user.id,
            target_username=payload.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DirectMessageStartResponse(threadId=thread.id, thread=thread)


@router.get("/threads", response_model=DirectMessageThreadList)
def list_threads(*, current_user=Depends(_get_current_user)) -> DirectMessageThreadList:
    from ..services import direct_messages as dm_service

    return dm_service.list_threads(current_user.id)


@router.get("/threads/{thread_id}/messages", response_model=DirectMessageList)
def list_thread_messages(
    thread_id: int,
    *,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    current_user=Depends(_get_current_user),
) -> DirectMessageList:
    from ..services import direct_messages as dm_service

    cursor_id = None
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor") from exc

    try:
        return dm_service.list_messages(
            thread_id,
            user_id=current_user.id,
            limit=limit,
            cursor=cursor_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/threads/{thread_id}/messages", response_model=DirectMessageSendResponse, status_code=201)
def send_thread_message(
    thread_id: int,
    payload: DirectMessageSendRequest,
    *,
    current_user=Depends(_get_current_user),
) -> DirectMessageSendResponse:
    from ..services import direct_messages as dm_service

    try:
        return dm_service.send_message(
            thread_id,
            user_id=current_user.id,
            sender_username=current_user.username,
            body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/threads/{thread_id}/read", response_model=DirectMessageMarkReadResponse)
def mark_thread_read(
    thread_id: int,
    *,
    current_user=Depends(_get_current_user),
) -> DirectMessageMarkReadResponse:
    from ..services import direct_messages as dm_service

    try:
        return dm_service.mark_thread_read(
            thread_id,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc