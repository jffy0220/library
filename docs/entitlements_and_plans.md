# Tier 1 Entitlements & Plans Specification

## Overview
This document defines the catalog of Tier 1 subscription plans, the entitlements granted by each plan, and the mechanism for calculating and propagating those entitlements to dependent services.

## Plan Catalog

### Individual (Pro)
- **Billing intervals**: monthly and annual.
- **Key capabilities**:
  - Ad-free experience across all clients.
  - Cloud sync for personal libraries and device backups.
  - Advanced features: OCR, advanced search, exports.
  - Baseline storage allotment of 100 GB.
- **Lifecycle rules**:
  - One active subscription per user account.
  - Downgrades revert to the Free plan at the end of the paid term unless an immediate downgrade is requested by support.

### Teams
- **Billing model**: per-seat with adjustable quantity.
- **Seat policies**:
  - Seat count must be greater than or equal to the number of active members.
  - Pending invites do not consume seats.
  - Seat overages trigger an immediate reconciliation process to either add seats or block new invites.
- **Capabilities**:
  - Includes all Individual entitlements for every team member.
  - Shared resources (libraries, collections, comments) become collaborative.
  - Team-level retention policies and administrative settings.
- **Lifecycle rules**:
  - Exactly one active subscription per organization.
  - Seat adjustments are effective immediately upon member change or admin update.

### Add-ons
- **Storage expansions**:
  - Sold in 100 GB increments.
  - Available to both Individual and Team plans.
  - Managed independently from the base subscription term; renew automatically unless canceled.
- **Future add-ons** (Tier 2 scope) should follow the same entitlement mapping model defined below.

## Entitlement Mapping

### Feature Flags
Each plan maps to an entitlement payload containing feature flags:
- `ads.disabled`: removes advertising surfaces.
- `sync.enabled`: unlocks background synchronization and device backups.
- `search.advanced`: enables OCR, semantic search, and saved search exports.
- `storage.quota_gb`: numeric quota derived from plan and add-ons.
- `org.admin`: for Team admins, unlocks organization settings, audit logs, and billing controls.

### Computation Rules
- Entitlements are derived from authoritative subscription records retrieved from the billing provider and internal seat rosters.
- For Team memberships, the entitlement payload is scoped per member with their role (owner/admin/member) to allow downstream permission checks.
- Add-on capacity is aggregated with base plan allocations before calculating quotas.
- Free tier users inherit a default entitlement payload with all premium flags disabled and minimal storage (e.g., 5 GB).

## Propagation & Caching
- Entitlements are computed per request through a centralized service that receives subscription identifiers from session context.
- A cache (e.g., Redis) stores entitlement payloads with a short TTL (≤ 5 minutes) to minimize recomputation.
- Cache invalidation triggers:
  - Billing webhook updates (subscription created/updated/canceled, payment failure).
  - Organization membership changes (invite accepted, role changed, member removed).
  - Manual administrator overrides executed by support tooling.
- After a cache invalidation, the next request rebuilds the payload using fresh data. Clients should not cache entitlements locally beyond the current session.

## Delivery to Clients
- Entitlements are embedded in signed tokens attached to API responses and websocket session handshakes.
- Web clients rely on the token to toggle UI affordances. Attempts to use gated APIs require server-side validation regardless of UI state.
- Mobile clients fetch entitlements through an authenticated API endpoint that returns the current payload and expiration timestamp.

## Acceptance Criteria
1. Plan changes are reflected in entitlement payloads no later than the next API request after processing the billing webhook.
2. Cache invalidation occurs automatically on subscription or membership updates without manual intervention.
3. Entitlement tokens are tamper-evident and expire within 10 minutes to limit replay risk.
4. Clients failing to refresh entitlements after expiration receive a 401/403 response prompting re-authentication.