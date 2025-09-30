# Tier 1 Organizations & Memberships Specification

## Organization Entity
- **Attributes**
  - `id`: globally unique identifier.
  - `name`: human-readable label shown in UI.
  - `owner_id`: user with irrevocable billing authority unless transferred.
  - `billing_contact_id`: user receiving billing notifications (defaults to owner).
  - `subscription_id`: linkage to active Team subscription.
  - `policy_flags`: JSON column controlling sharing, retention, export permissions.
  - `created_at` / `updated_at`: timestamps for audit trail.
- **Constraints**
  - One active Team subscription per organization.
  - Deleting an organization requires cancellation of the subscription and archival of data per retention policy.

## Roles & Permissions
- **Owner**
  - Full administrative rights, including billing, member management, policy configuration.
  - Can transfer ownership to another admin.
- **Admin**
  - Manage members, view audit logs, configure policies.
  - Initiate billing actions if `billing_admin` flag is granted.
- **Member**
  - Access shared libraries/collections based on resource-level permissions.
  - Cannot modify billing or policy settings.

## Membership Lifecycle
1. **Invitation**
   - Owner/admin sends invite via email; system generates signed token valid for 7 days.
   - Invite records track role to be assigned upon acceptance.
   - Inviter cannot assign a role higher than their own.
2. **Acceptance**
   - Invitee authenticates (or creates account) and redeems token.
   - Seat consumption occurs at acceptance time; entitlements recalc for org members.
3. **Revocation**
   - Owners/admins can remove members instantly; seat count decremented.
   - Revoked users lose access tokens to shared resources immediately.
4. **Role Changes**
   - Owner/admin may upgrade/downgrade member roles; owner role transfer requires acceptance by target user.
   - All changes recorded with actor, target, timestamp, previous/new role.

## Shared Resources
- Libraries and collections have an `organization_id` and permission model supporting read/write/admin scopes.
- Comments and annotations reference both the resource and membership context for auditing.
- Export, backup, and retention settings are accessible only to owners/admins with appropriate flags.

## Seat Accounting Rules
- Count only members with status `active`.
- Pending invites, suspended accounts, or guests (read-only link viewers) do not consume seats.
- Seat adjustments propagate to billing reconciliation queue immediately after membership events.
- Historical seat usage is recorded daily for analytics and overage dispute resolution.

## Audit Logging
- Every membership mutation emits an event captured in the audit log service with fields: actor, organization, subject, action, metadata, timestamp.
- Audit events are immutable and retained for at least 13 months.
- Admin UI provides filters by action type (invite, remove, role_change) and date range.

## Acceptance Criteria
1. Role assignment UI prevents selection of unauthorized roles before request submission.
2. Removing a member revokes their access tokens within 60 seconds and decrements seat count.
3. Audit log entries are generated for invitations, acceptances, removals, and role changes with correct metadata.
4. Organization deletion is blocked until subscription cancellation is confirmed and all data exports are completed.