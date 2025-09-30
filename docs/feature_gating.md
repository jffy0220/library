# Tier 1 Feature Gating Specification

## Scope
Enumerates the product surfaces and backend services that must enforce Tier 1 entitlements, and describes how gating is validated end-to-end.

## Gated Surfaces
- **Advertising**
  - Web and mobile clients suppress ad components when `ads.disabled` entitlement is true.
  - Server-rendered pages check entitlement before injecting ad slots.
- **Cloud Sync & Backups**
  - Sync API verifies `sync.enabled` before scheduling background sync jobs.
  - Backup exports require both `sync.enabled` and sufficient storage quota.
- **Advanced Functionality**
  - OCR requests verify `search.advanced` flag and log usage metrics.
  - Advanced search endpoints return 403 if entitlement missing, with error code `entitlement_required`.
  - Bulk export (CSV/PDF) endpoints require premium entitlement and enforce rate limits per plan.
- **Storage Quotas**
  - Upload service checks `storage.quota_gb` against current utilization stored in usage service.
  - Storage overage triggers warnings and blocks additional uploads after configurable threshold (e.g., 110% of quota).

## Enforcement Layers
1. **API Gateway**
   - Injects entitlement payload into request context for downstream services.
   - Rejects requests lacking valid entitlement token with 401.
2. **Service-Level Checks**
   - Each gated endpoint performs explicit entitlement validation using shared library.
   - Shared library exposes helpers `require_entitlement(flag)` and `assert_quota(usage, quota)`.
3. **Client-Side UX**
   - UI hides premium controls when entitlements absent but still handles server rejection gracefully.
   - Paid-only badges include tooltip linking to upgrade flow.

## Monitoring & Alerts
- Track entitlement check failures per endpoint to detect regressions.
- Configure alert when failure rate exceeds 5% over 15 minutes for paid users (indicates propagation issue).
- Log storage quota denials with user/org metadata for support visibility.

## Testing Strategy
- Automated tests simulate entitlement tokens for Free vs Paid to verify enforcement at API and service layers.
- UI integration tests ensure upgrade prompts appear when entitlements missing.
- Regression checklist includes manual testing of upgrade/downgrade flows to confirm gating transitions.

## Acceptance Criteria
1. Unauthorized access attempts to gated APIs result in consistent 403 responses with actionable error payloads.
2. Storage quota enforcement prevents uploads beyond allocated capacity and notifies users of remaining quota.
3. Monitoring dashboards display entitlement validation metrics with per-plan breakdowns.
4. UX gracefully guides Free users toward upgrade without exposing premium functionality.