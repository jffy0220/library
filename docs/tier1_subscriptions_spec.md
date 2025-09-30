# Tier 1 Subscriptions and Teams Functional Specification

## Overview
This document describes the functional requirements for Tier 1 subscription offerings, covering individual Pro plans and per-seat Team plans. It defines entitlements, billing flows, organizational behaviors, feature gating, and policy considerations necessary to deliver a compliant subscription experience.

## A. Entitlements & Plans

### Plan Catalog
- **Individual (Pro)**: Available in monthly and annual billing intervals.
- **Teams**: Single active subscription per organization with adjustable seat counts aligned to active membership.
- **Add-ons**: Optional storage expansions (detailed separately in Tier 2 scope).

### Entitlements Model
- Entitlements are computed per request using authoritative subscription data, mapping plans to feature flags such as:
  - Advertisement suppression for paid tiers.
  - Cloud sync enablement for paid tiers.
  - Storage quota allocation, including add-on capacity.
  - Permissions for exports, OCR, and advanced search.
- Entitlements are exposed through a trusted channel (request context or signed token) so downstream API handlers and web clients can enforce gating without additional database lookups.

### Propagation & Caching
- A plan change must propagate new entitlements within a single request cycle after receiving confirmation from the billing webhook.
- Entitlement caches are invalidated on billing webhook events and on organization membership changes to keep seat-based permissions accurate.

### Acceptance Criteria
- Plan changes reflect in entitlements immediately after webhook acknowledgement.
- Cached entitlements refresh automatically when triggered by subscription or membership updates.

## B. Billing Flows

### Checkout
1. User selects a plan tier.
2. System creates a checkout session with the billing provider and stores a pending purchase intent tied to the individual account or organization.
3. User is redirected to the provider for payment.
4. Upon return, the application displays subscription status sourced from the provider to avoid relying on local state.

### Customer Portal
- Provide a self-service portal link for active subscribers to update payment methods, review invoices, and manage cancellations.

### Webhooks
- Listen to subscription lifecycle events: created, updated, canceled, payment failed.
- Update internal subscription records and recompute entitlements on each event.
- For Team plans, synchronize seat quantities with the count of active billable members. Trigger reconciliation after every membership modification.

### Invoices & Receipts
- Persist provider invoice identifiers for audit and support.
- Expose invoice listings to users with billing permissions.

### Acceptance Criteria
- Paid features remain locked until a confirming webhook from the provider is processed.
- Failed payments initiate grace periods before reverting accounts to the free tier with clear notifications.
- Team seat counts remain synchronized with active membership, including rapid add/remove sequences.

## C. Organizations & Memberships (Teams)

### Organization Entity
- Attributes: name, owner, billing contact, subscription linkage, and policy flags governing sharing and retention.

### Membership Management
- Roles: owner, admin, member.
- Invite flow issues email-based tokens; invitees cannot receive a higher role than the inviter is allowed to assign.
- Revocation flow removes members immediately, revoking resource access and reducing seat counts.
- All membership joins and leaves generate auditable events.

### Shared Resources
- Shared libraries and collections, collaborative comments, and role-gated settings for exports, backups, and retention policies.

### Seat Accounting
- Count only active members toward seat usage; exclude pending invitations.
- Adjust seat quantities instantly when members accept invites or are revoked.

### Acceptance Criteria
- Role assignments respect inviter privileges.
- Removing a member immediately revokes access and decrements billable seats.
- Every organizational mutation is captured in audit logs.

## D. Feature Gating Surfaces

- **Ads**: Remove advertisements for users with paid entitlements.
- **Cloud Sync & Backups**: Enable for paid users and teams.
- **Advanced Functionality**: Gate OCR, advanced search, and exporters behind paid entitlements.
- **Storage**: Increase quotas for paid plans and apply storage add-ons.

### Acceptance Criteria
- Server-side enforcement ensures clients cannot bypass restrictions through local modifications.
- APIs validate entitlements for all gated operations, preventing unauthorized access even if UI elements are tampered with.

## E. Policy, Compliance, and Security

- **Privacy**: Paid features must operate without third-party trackers; analytics remain first-party only.
- **Refunds & Cancellations**: Policies are documented, and grace periods are enforced by the entitlements engine.
- **Security**: Payment card data is handled exclusively by the billing provider to maintain PCI compliance; no card information persists on platform servers.