"""Feature gating utilities coordinating entitlement enforcement."""
from .context import EntitlementContext
from .enforcement import require_entitlement
from .exceptions import FeatureGateError
from .quota import StorageQuotaEvaluation, assert_quota, evaluate_storage_quota

__all__ = [
    "EntitlementContext",
    "FeatureGateError",
    "StorageQuotaEvaluation",
    "assert_quota",
    "evaluate_storage_quota",
    "require_entitlement",
]