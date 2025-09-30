"""Helpers for enforcing entitlement checks on API and service layers."""
from __future__ import annotations

from typing import Mapping

from .exceptions import FeatureGateError


def require_entitlement(
    feature_flags: Mapping[str, object],
    flag: str,
    *,
    error_code: str = "entitlement_required",
    message: str | None = None,
) -> None:
    """Ensure a boolean feature flag is enabled before proceeding.

    Parameters
    ----------
    feature_flags:
        Mapping of entitlement flags as provided by :class:`EntitlementPayload`.
    flag:
        The canonical feature flag that must evaluate truthy.
    error_code:
        Optional override for the surfaced error code when the entitlement is
        not granted. Defaults to ``"entitlement_required"``.
    message:
        Optional human-friendly message explaining the failure. If omitted, a
        default message mentioning the missing flag is used.
    """

    value = feature_flags.get(flag)
    is_enabled = bool(value)

    if not is_enabled:
        failure_message = message or f"Entitlement '{flag}' is required."
        raise FeatureGateError(
            code=error_code,
            message=failure_message,
            detail={"missing_entitlement": flag},
        )