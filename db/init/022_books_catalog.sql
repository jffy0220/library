CREATE TABLE IF NOT EXISTS book_catalog (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT NULL,
  isbn TEXT NULL,
  google_volume_id TEXT NULL,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_book_catalog_unique
  ON book_catalog (LOWER(TRIM(title)), LOWER(TRIM(COALESCE(author, ''))));

CREATE INDEX IF NOT EXISTS idx_book_catalog_title
  ON book_catalog (LOWER(TRIM(title)));

CREATE INDEX IF NOT EXISTS idx_book_catalog_author
  ON book_catalog (LOWER(TRIM(author)));