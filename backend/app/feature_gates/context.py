"""Convenience wrapper around entitlement payloads for feature gating."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Union

from ..entitlements import EntitlementPayload
from .enforcement import require_entitlement
from .quota import StorageQuotaEvaluation, assert_quota, evaluate_storage_quota


@dataclass(frozen=True)
class EntitlementContext:
    """Facade exposing gating-centric helpers for a subject's entitlements."""

    payload: EntitlementPayload

    @property
    def feature_flags(self) -> Dict[str, Union[int, bool]]:
        return dict(self.payload.feature_flags)

    @property
    def plan(self):
        return self.payload.plan

    @property
    def role(self):
        return self.payload.role

    @property
    def storage_quota_gb(self) -> int:
        return self.payload.storage_quota_gb

    def has(self, flag: str) -> bool:
        """Return whether the provided flag evaluates truthy."""

        return bool(self.payload.feature_flags.get(flag))

    def require(self, flag: str, *, error_code: str = "entitlement_required") -> None:
        """Ensure an entitlement flag is present and enabled."""

        require_entitlement(self.payload.feature_flags, flag, error_code=error_code)

    def evaluate_storage_quota(
        self,
        *,
        usage_gb: float,
        pending_upload_gb: float = 0.0,
        threshold: Optional[float] = None,
    ) -> StorageQuotaEvaluation:
        """Inspect whether storage operations should proceed or warn."""

        effective_threshold = threshold if threshold is not None else 1.10
        return evaluate_storage_quota(
            usage_gb=usage_gb,
            quota_gb=self.storage_quota_gb,
            pending_upload_gb=pending_upload_gb,
            threshold=effective_threshold,
        )

    def assert_storage_quota(
        self,
        *,
        usage_gb: float,
        pending_upload_gb: float = 0.0,
        threshold: Optional[float] = None,
        error_code: str = "storage_quota_exceeded",
    ) -> StorageQuotaEvaluation:
        """Raise when projected storage usage violates the entitlement quota."""

        effective_threshold = threshold if threshold is not None else 1.10
        return assert_quota(
            usage_gb=usage_gb,
            quota_gb=self.storage_quota_gb,
            pending_upload_gb=pending_upload_gb,
            threshold=effective_threshold,
            error_code=error_code,
        )