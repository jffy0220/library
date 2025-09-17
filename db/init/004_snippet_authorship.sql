-- Track snippet ownership by linking snippets to the creating user.
ALTER TABLE snippets
  ADD COLUMN IF NOT EXISTS created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_snippets_created_by ON snippets(created_by_user_id);