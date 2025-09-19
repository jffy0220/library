-- Store optional email addresses for authentication flows.
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS email TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower
  ON users ((LOWER(email)))
  WHERE email IS NOT NULL;
