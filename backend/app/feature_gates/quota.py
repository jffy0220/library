+93
-0

"""Storage quota evaluation utilities for feature gating."""
from __future__ import annotations

from dataclasses import dataclass

from .exceptions import FeatureGateError

_DEFAULT_BLOCK_THRESHOLD = 1.10


@dataclass(frozen=True)
class StorageQuotaEvaluation:
    """Represents the outcome of a storage quota check."""

    quota_gb: int
    current_usage_gb: float
    pending_upload_gb: float
    projected_usage_gb: float
    threshold: float
    should_warn: bool
    allowed: bool

    def to_dict(self) -> dict[str, float | int | bool]:
        """Serialize the evaluation for logging or telemetry."""

        return {
            "quota_gb": self.quota_gb,
            "current_usage_gb": self.current_usage_gb,
            "pending_upload_gb": self.pending_upload_gb,
            "projected_usage_gb": self.projected_usage_gb,
            "threshold": self.threshold,
            "should_warn": self.should_warn,
            "allowed": self.allowed,
        }


def evaluate_storage_quota(
    *,
    usage_gb: float,
    quota_gb: int,
    pending_upload_gb: float = 0.0,
    threshold: float = _DEFAULT_BLOCK_THRESHOLD,
) -> StorageQuotaEvaluation:
    """Determine whether a storage operation is permitted under quota rules."""

    projected_usage = usage_gb + max(pending_upload_gb, 0.0)
    warn_threshold = float(quota_gb)
    block_threshold = float(quota_gb) * threshold

    should_warn = projected_usage >= warn_threshold
    allowed = projected_usage <= block_threshold

    return StorageQuotaEvaluation(
        quota_gb=quota_gb,
        current_usage_gb=usage_gb,
        pending_upload_gb=max(pending_upload_gb, 0.0),
        projected_usage_gb=projected_usage,
        threshold=threshold,
        should_warn=should_warn,
        allowed=allowed,
    )


def assert_quota(
    *,
    usage_gb: float,
    quota_gb: int,
    pending_upload_gb: float = 0.0,
    threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    error_code: str = "storage_quota_exceeded",
) -> StorageQuotaEvaluation:
    """Raise when a storage operation exceeds the configured quota."""

    evaluation = evaluate_storage_quota(
        usage_gb=usage_gb,
        quota_gb=quota_gb,
        pending_upload_gb=pending_upload_gb,
        threshold=threshold,
    )

    if not evaluation.allowed:
        raise FeatureGateError(
            code=error_code,
            message="Storage quota exceeded.",
            detail={
                "quota_gb": quota_gb,
                "usage_gb": round(evaluation.projected_usage_gb, 2),
                "pending_upload_gb": round(max(pending_upload_gb, 0.0), 2),
                "threshold": threshold,
            },
        )

    return evaluation