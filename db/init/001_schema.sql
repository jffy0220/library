-- PostgreSQL schema for book snippets (all fields optional).
CREATE TABLE IF NOT EXISTS snippets (
  id BIGSERIAL PRIMARY KEY,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  date_read DATE NULL,
  book_name VARCHAR(255) NULL,
  page_number INT NULL,
  chapter VARCHAR(100) NULL,
  verse VARCHAR(100) NULL,
  text_snippet TEXT NULL,
  thoughts TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_book_date ON snippets (book_name, date_read);
CREATE INDEX IF NOT EXISTS idx_text_search
  ON snippets USING GIN (to_tsvector('english', coalesce(text_snippet,'') || ' ' || coalesce(thoughts,'')));
