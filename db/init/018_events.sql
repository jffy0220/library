-- Create append-only analytics table
CREATE TABLE IF NOT EXISTS app_events (
  id           BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id      TEXT,
  anonymous_id TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  event        TEXT NOT NULL,
  route        TEXT,
  ip_hash      TEXT,
  user_agent   TEXT,
  duration_ms  INTEGER,
  props        JSONB NOT NULL DEFAULT '{}'::jsonb,
  context      JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_app_events_ts           ON app_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_app_events_event_ts     ON app_events (event, ts DESC);
CREATE INDEX IF NOT EXISTS idx_app_events_user_ts      ON app_events (user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_app_events_props_gin    ON app_events USING GIN (props);