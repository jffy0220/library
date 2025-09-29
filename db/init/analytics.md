# Analytics Overview

This application ships with first-party analytics that record application usage, reliability, and performance without relying on third-party vendors. Events are stored in Postgres inside the `app_events` table (`db/init/018_events.sql`). The table is append-only and accepts schemaless properties via `JSONB` so the schema can evolve without destructive migrations.

Analytics ingestion is controlled by the `ANALYTICS_ENABLED` feature flag on both the backend and the frontend. When disabled the API and client safely no-op. Additional context such as the current app version can be provided through the optional `APP_VERSION` environment variable (backend) or `VITE_APP_VERSION` (frontend) so events can be correlated with deployments.

## Storage Schema

Each event row includes the following common fields:

| Column | Description |
| --- | --- |
| `ts` | Event timestamp (defaults to `now()` in UTC) |
| `user_id` | Optional application user id (text) |
| `anonymous_id` | Stable per-device identifier |
| `session_id` | Stable per-session identifier |
| `event` | Event name (snake_case) |
| `route` | SPA route when the event was captured |
| `ip_hash` | `sha256(ip + ANALYTICS_IP_SALT)`; never stores raw IPs |
| `user_agent` | Raw user-agent string (frontend ingestion only) |
| `duration_ms` | Optional duration in milliseconds for latency/perf events |
| `props` | Event-specific properties (`JSONB`) |
| `context` | Additional context (source, app version, etc.; `JSONB`) |

Helpful indexes are created on `ts`, `event`, `user_id`, and a GIN index on `props` for ad-hoc querying.

## Event Taxonomy

Event names are stable; evolve payloads by adding new keys to `props` instead of renaming events.

### Identity & Session

| Event | Properties |
| --- | --- |
| `user_signed_up` | `{ has_email }` |
| `user_logged_in` | – |
| `user_logged_out` | – |

### Core Product

| Event | Properties |
| --- | --- |
| `snippet_created` | `{ length, has_thoughts, book_id, tags_count, source }` |
| `snippet_edited` | `{ changed_fields, source }` |
| `snippet_deleted` | `{ snippet_id, source }` |
| `book_created` | `{ book_id }` *(future)* |
| `tag_created` | `{ name }` *(future)* |
| `tag_added_to_snippet` | `{ tag_id, snippet_id }` *(future)* |
| `collection_created` | `{ collection_id }` *(future)* |
| `collection_item_added` | `{ collection_id, snippet_id }` *(future)* |

### Import & Export

| Event | Properties |
| --- | --- |
| `import_started` | `{ type, rows_expected }` *(future)* |
| `import_completed` | `{ type, rows_imported, errors }` *(future)* |
| `export_performed` | `{ format }` *(future)* |

### Search Quality

| Event | Properties |
| --- | --- |
| `search_performed` | `{ q_len, filters: { tags, book, date_range }, results_count }` (duration stored in `duration_ms`) |
| `search_zero_results` | `{ q, filters }` |

### UX & Performance

| Event | Properties |
| --- | --- |
| `page_view` | – |
| `web_vital` | `{ name, value }` |
| `frontend_error` | `{ message, stack?, filename?, lineno?, colno? }` |
| `http_request` | `{ method, status }` (duration stored in `duration_ms`) |

Backend mirror events always include `context.source = "api"`; frontend events default to `context.source = "web"`. When `APP_VERSION`/`VITE_APP_VERSION` is set the value is merged into event context automatically.

## Naming Conventions

* Event names are `snake_case`.
* `props` keys stay flat and prefer lower_snake_case for compatibility with Postgres JSON queries.
* `context` keys are also flat and reserved for transport metadata such as `source` or `app_version`.
* Extend payloads by adding new keys; do not rename existing properties.

## Privacy & PII Policy

* Raw IP addresses are never persisted. The ingestion API hashes IPs with `sha256(ip + ANALYTICS_IP_SALT)` and stores only the hash.
* Do not log passwords, tokens, or other sensitive secrets in `props` or `context`.
* Keep event payloads focused on product metrics (counts, booleans, identifiers) rather than free-form text that could include PII.

## Retention

* Raw `app_events` rows are retained for **90 days**.
* Aggregated metrics and derived reports may be kept indefinitely.

## Adding a New Event

1. **Frontend capture** – leverage the batching client in `frontend/src/lib/analytics.ts`:

   ```ts
   import { capture } from '../lib/analytics'

   capture({
     event: 'tag_created',
     props: {
       name: tagName,
       source: 'web'
     }
   })
   ```

   Events are queued and posted to `/analytics/collect` every 2.5s (or on pagehide/beforeunload). Errors are swallowed so user flows are unaffected.

2. **Backend mirror** – for critical flows emit the same event server-side after the database commit using the helper utilities in `backend/main.py`:

   ```py
   props = {"collection_id": new_collection_id, "source": "api"}
   event = _build_server_event(
       "collection_created",
       request=request,
       user_id=current_user.id,
       props=props,
   )
   _queue_analytics_event(event)
   ```

   Server mirrors ensure events are recorded even when clients are offline or ad blockers intercept network requests.

3. **Run tests / lint** as needed, update docs, and deploy.

## Sample Queries

```sql
-- Daily snippet creation trend
SELECT date_trunc('day', ts) AS day, count(*) AS events
FROM app_events
WHERE event = 'snippet_created'
GROUP BY 1
ORDER BY 1;

-- Signup to first snippet activation within 7 days
WITH signups AS (
  SELECT user_id, min(ts) ts FROM app_events WHERE event='user_signed_up' GROUP BY 1
),
first_snip AS (
  SELECT user_id, min(ts) ts FROM app_events WHERE event='snippet_created' GROUP BY 1
)
SELECT
  count(*) FILTER (WHERE s.user_id IS NOT NULL) AS signups,
  count(*) FILTER (WHERE f.user_id IS NOT NULL AND f.ts <= s.ts + interval '7 days') AS activated_7d
FROM signups s
LEFT JOIN first_snip f USING (user_id);

-- Zero-result search rate
SELECT
  date_trunc('day', ts) AS day,
  100.0 * sum(CASE WHEN event='search_zero_results' THEN 1 ELSE 0 END)
  / NULLIF(sum(CASE WHEN event='search_performed' THEN 1 ELSE 0 END),0) AS zero_result_pct
FROM app_events
WHERE event IN ('search_performed','search_zero_results')
GROUP BY 1
ORDER BY 1;
```

## Feature Flags & Environment

* Backend: `ANALYTICS_ENABLED`, `ANALYTICS_IP_SALT`, `APP_VERSION`
* Frontend: `VITE_ANALYTICS_ENABLED`, optional `VITE_APP_VERSION`

Keep salts and secrets out of version control. Rotate `ANALYTICS_IP_SALT` if compromised.