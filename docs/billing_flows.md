# Tier 1 Billing Flows Specification

## Overview
Defines the checkout, subscription management, webhook handling, and financial record keeping required to support Tier 1 paid subscriptions.

## Checkout Experience
1. **Plan selection**
   - Display pricing cards for Individual monthly, Individual annual, and Team plans with seat selector.
   - Collect billing country to determine tax requirements before redirecting to provider.
2. **Checkout session creation**
   - Create a billing provider checkout session with metadata: user/org identifier, plan ID, seat quantity (for Teams), return URL, cancel URL.
   - Persist a pending `purchase_intent` record referencing the initiating actor and selected plan.
3. **Redirect & confirmation**
   - Redirect the user to the provider-hosted checkout page.
   - After payment, the provider redirects to the success URL with a session identifier.
   - The application polls the provider API to retrieve session status; UI displays "Processing" until a webhook confirms activation.
4. **Failure handling**
   - If the provider indicates an abandoned or failed session, mark the `purchase_intent` as expired and surface retry messaging.

## Customer Portal
- Provide a "Manage billing" link in account or organization settings for active subscribers.
- Portal grants abilities to:
  - Update payment method.
  - View invoices and receipts.
  - Change seat counts (Teams) when supported by provider.
  - Cancel or schedule cancellation.
- Access to the portal is restricted to billing owners (Individual subscriber or Team owner/admin with billing privileges).

## Subscription Lifecycle Webhooks
- Subscribe to provider events: `subscription.created`, `subscription.updated`, `subscription.canceled`, `invoice.payment_failed`, `invoice.payment_succeeded`.
- On receipt:
  1. Verify the webhook signature.
  2. Fetch the latest subscription object from the provider to avoid relying on payload deltas.
  3. Update internal subscription record: status, current period dates, trial flags, seat quantity, applied coupons.
  4. Trigger entitlement cache invalidation for affected users/organizations.
  5. Emit audit events for downstream processing (analytics, notifications).
- Webhook processing must be idempotent; store the last processed event ID to guard against duplicates.

## Seat Synchronization (Teams)
- After every membership change, enqueue a reconciliation job that compares active member count with subscription seats.
- If member count exceeds seats:
  - Attempt to update the subscription via provider API to increase seats automatically.
  - If automatic update fails, notify the owner and restrict additional invites.
- If seats exceed members for more than 24 hours, prompt the owner to reduce seats or retain buffer capacity.

## Invoices & Receipts
- Persist invoice records with fields: provider invoice ID, amount, currency, period covered, PDF URL, payment status.
- Expose an API for billing owners to list invoices, filtered by organization or user context.
- Email receipts automatically upon successful payment, using provider-hosted PDF when available.
- Support proration details in UI when seats are added mid-cycle.

## Payment Failures & Grace Periods
- On `invoice.payment_failed`:
  - Mark subscription as `past_due` and start a configurable grace period (default 7 days).
  - Notify billing contacts via email and in-app banner with retry instructions.
- During grace period, paid entitlements remain active but UI surfaces warnings.
- If payment succeeds within grace period, clear the warning and return to `active` status.
- If grace period lapses without payment, downgrade to Free tier and revoke premium entitlements.

## Acceptance Criteria
1. Paid features remain locked until a confirming webhook activates the subscription.
2. Manual refresh or retries of webhook processing do not create duplicate subscription records.
3. Seat counts shown in the UI match the provider's record after reconciliation completes.
4. Grace period expirations are recorded in audit logs, and affected users receive downgrade notifications.