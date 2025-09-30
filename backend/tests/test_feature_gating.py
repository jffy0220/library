from __future__ import annotations

import pytest

from backend.app.entitlements import EntitlementPayload, MembershipRole, PlanKey
from backend.app.feature_gates import (
    EntitlementContext,
    FeatureGateError,
    StorageQuotaEvaluation,
    evaluate_storage_quota,
    require_entitlement,
)


@pytest.fixture
def entitlement_payload() -> EntitlementPayload:
    return EntitlementPayload(
        plan=PlanKey.INDIVIDUAL_PRO,
        feature_flags={
            "ads.disabled": True,
            "sync.enabled": True,
            "search.advanced": True,
            "storage.quota_gb": 100,
        },
        subscription_id="sub-123",
        organization_id="org-1",
        role=MembershipRole.ADMIN,
    )


def test_require_entitlement_allows_enabled_flag(entitlement_payload: EntitlementPayload) -> None:
    require_entitlement(entitlement_payload.feature_flags, "sync.enabled")


def test_require_entitlement_raises_when_missing(entitlement_payload: EntitlementPayload) -> None:
    with pytest.raises(FeatureGateError) as exc:
        require_entitlement(entitlement_payload.feature_flags, "nonexistent.flag")

    assert exc.value.code == "entitlement_required"
    assert exc.value.payload["missing_entitlement"] == "nonexistent.flag"


def test_entitlement_context_helpers(entitlement_payload: EntitlementPayload) -> None:
    context = EntitlementContext(entitlement_payload)

    assert context.has("ads.disabled") is True
    assert context.has("bulk.export") is False

    context.require("search.advanced")

    with pytest.raises(FeatureGateError):
        context.require("bulk.export")


def test_storage_quota_evaluation_warns_before_block(entitlement_payload: EntitlementPayload) -> None:
    evaluation = evaluate_storage_quota(usage_gb=95, quota_gb=100, pending_upload_gb=10)

    assert isinstance(evaluation, StorageQuotaEvaluation)
    assert evaluation.should_warn is True
    assert evaluation.allowed is True


def test_assert_quota_blocks_when_threshold_exceeded(entitlement_payload: EntitlementPayload) -> None:
    context = EntitlementContext(entitlement_payload)

    with pytest.raises(FeatureGateError) as exc:
        context.assert_storage_quota(usage_gb=105, pending_upload_gb=10)

    assert exc.value.code == "storage_quota_exceeded"
    assert exc.value.payload["quota_gb"] == 100
    assert exc.value.payload["usage_gb"] == pytest.approx(115)


def test_feature_gate_error_converts_to_http_exception(entitlement_payload: EntitlementPayload) -> None:
    error = FeatureGateError(code="entitlement_required", message="flag missing")
    http_exc = error.to_http_exception()

    assert http_exc.status_code == 403
    assert http_exc.detail["error"] == "entitlement_required"