-- Store per-user onboarding and password reset tokens with persistence.
CREATE TABLE IF NOT EXISTS user_tokens (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_type TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  email TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_tokens_user_type_idx
  ON user_tokens (user_id, token_type);
CREATE INDEX IF NOT EXISTS user_tokens_lookup_idx
  ON user_tokens (token_type, token_hash);
CREATE INDEX IF NOT EXISTS user_tokens_expiry_idx
  ON user_tokens (expires_at);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'user_tokens_token_type_check'
      AND conrelid = 'user_tokens'::regclass
  ) THEN
    ALTER TABLE user_tokens
      ADD CONSTRAINT user_tokens_token_type_check
      CHECK (token_type IN ('onboarding', 'password_reset'));
  END IF;
END $$;
