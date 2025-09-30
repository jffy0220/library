from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import asyncpg

from .analytics_config import ANALYTICS_ENABLED, APP_VERSION, DB_CONFIG

from .analytics_config import (
    ANALYTICS_ENABLED,
    APP_VERSION,
    DB_CONFIG,
    DB_CONNECT_TIMEOUT,
)


LOGGER = logging.getLogger("analytics.queue")


INSERT_SQL = """
    INSERT INTO app_events (
        ts,
        user_id,
        anonymous_id,
        session_id,
        event,
        route,
        ip_hash,
        user_agent,
        duration_ms,
        props,
        context
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb
    )
"""


def _ensure_json(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {})


def _normalize_ts(value: Optional[datetime], fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _with_app_version(event: Dict[str, Any]) -> Dict[str, Any]:
    if APP_VERSION:
        context = dict(event.get("context") or {})
        context.setdefault("app_version", APP_VERSION)
        event["context"] = context
    return event


async def create_analytics_pool() -> Optional[asyncpg.Pool]:
    if not ANALYTICS_ENABLED:
        return None
    return await asyncpg.create_pool(
        min_size=1,
        max_size=5,
        command_timeout=10,
        timeout=DB_CONNECT_TIMEOUT,
        **DB_CONFIG,
    )
    return await asyncpg.create_pool(min_size=1, max_size=5, command_timeout=10, **DB_CONFIG)


async def insert_events(
    pool: asyncpg.Pool,
    events: Iterable[Dict[str, Any]],
) -> int:
    payload: List[List[Any]] = []
    now = datetime.now(timezone.utc)
    for event in events:
        normalized = _with_app_version(dict(event))
        ts = _normalize_ts(normalized.get("ts"), now)
        payload.append(
            [
                ts,
                normalized.get("user_id"),
                normalized.get("anonymous_id"),
                normalized.get("session_id"),
                normalized.get("event"),
                normalized.get("route"),
                normalized.get("ip_hash"),
                normalized.get("user_agent"),
                normalized.get("duration_ms"),
                _ensure_json(normalized.get("props")),
                _ensure_json(normalized.get("context")),
            ]
        )

    if not payload:
        return 0

    async with pool.acquire() as connection:
        await connection.executemany(INSERT_SQL, payload)
    return len(payload)


class AnalyticsQueue:
    def __init__(
        self,
        *,
        pool: Optional[asyncpg.Pool],
        loop: asyncio.AbstractEventLoop,
        enabled: bool,
    ) -> None:
        self._pool = pool
        self._loop = loop
        self.enabled = enabled and pool is not None
        self._queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=10_000)
        self._closed = False

    def put_nowait(self, event: Dict[str, Any]) -> None:
        if not self.enabled or self._closed:
            return
        payload = _with_app_version(dict(event))
        self._loop.call_soon_threadsafe(self._enqueue, payload)

    def _enqueue(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            LOGGER.warning("Analytics queue is full; dropping event")

    async def run(self) -> None:
        if not self.enabled or self._pool is None:
            return
        try:
            while not self._closed:
                event = await self._queue.get()
                batch = [event]
                while len(batch) < 200:
                    try:
                        batch.append(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                try:
                    await insert_events(self._pool, batch)
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("Failed to persist analytics batch")
                finally:
                    for _ in batch:
                        self._queue.task_done()
        except asyncio.CancelledError:
            await self.flush()
            raise

    def close(self) -> None:
        self._closed = True

    async def flush(self) -> None:
        if not self.enabled or self._pool is None:
            return
        items: List[Dict[str, Any]] = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:  # pragma: no cover - race guard
                break
        if items:
            try:
                await insert_events(self._pool, items)
            finally:
                for _ in items:
                    self._queue.task_done()
