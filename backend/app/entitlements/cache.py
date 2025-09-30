"""Cache abstractions for entitlement payloads."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Protocol, Set

from .models import EntitlementResult


class EntitlementCache(Protocol):
    """Protocol describing cache operations used by the entitlement service."""

    def get(self, key: str) -> Optional[EntitlementResult]:
        ...

    def set(self, key: str, value: EntitlementResult, expires_at: datetime, tags: Set[str]) -> None:
        ...

    def invalidate(self, tags: Iterable[str]) -> None:
        ...


@dataclass
class _CacheEntry:
    value: EntitlementResult
    expires_at: datetime
    tags: Set[str]

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class InMemoryEntitlementCache:
    """Simple in-memory cache suitable for tests and local development."""

    def __init__(self) -> None:
        self._entries: Dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[EntitlementResult]:
        now = datetime.now(timezone.utc)
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.is_expired(now):
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(
        self,
        key: str,
        value: EntitlementResult,
        expires_at: datetime,
        tags: Set[str],
    ) -> None:
        now = datetime.now(timezone.utc)
        if expires_at <= now:
            return
        self._entries[key] = _CacheEntry(value=value, expires_at=expires_at, tags=set(tags))

    def invalidate(self, tags: Iterable[str]) -> None:
        tag_set = set(tags)
        if not tag_set:
            return
        keys_to_delete = [
            key
            for key, entry in self._entries.items()
            if entry.tags.intersection(tag_set)
        ]
        for key in keys_to_delete:
            self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()