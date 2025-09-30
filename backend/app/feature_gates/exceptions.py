"""Custom exceptions used for feature gating enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from fastapi import HTTPException, status


@dataclass
class FeatureGateError(Exception):
    """Represents an actionable gating failure surfaced to API callers."""

    code: str
    message: str
    status_code: int = status.HTTP_403_FORBIDDEN
    detail: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        base_detail: Dict[str, Any] = {"error": self.code, "message": self.message}
        if self.detail:
            base_detail.update(self.detail)
        object.__setattr__(self, "_payload", base_detail)
        super().__init__(self.message)

    @property
    def payload(self) -> Mapping[str, Any]:
        """Serialized representation suitable for JSON responses."""

        return self._payload

    def to_http_exception(self) -> HTTPException:
        """Convert the domain error into a FastAPI HTTPException."""

        return HTTPException(status_code=self.status_code, detail=dict(self.payload))