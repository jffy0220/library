-- Lightweight moderation flags for snippets and comments.
CREATE TABLE IF NOT EXISTS content_flags (
  id BIGSERIAL PRIMARY KEY,
  content_type TEXT NOT NULL CHECK (content_type IN ('snippet', 'comment')),
  content_id BIGINT NOT NULL,
  reporter_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason TEXT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_utc TIMESTAMPTZ NULL,
  resolved_by_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  resolution_note TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_flags_status ON content_flags(status);
CREATE INDEX IF NOT EXISTS idx_flags_content ON content_flags(content_type, content_id);
CREATE INDEX IF NOT EXISTS idx_flags_reporter ON content_flags(reporter_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_flags_unique_open
  ON content_flags(content_type, content_id, reporter_id)
  WHERE status = 'open';