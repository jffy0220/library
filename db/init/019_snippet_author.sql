-- Add support for storing the original author of a snippet selection.
ALTER TABLE snippets
  ADD COLUMN IF NOT EXISTS book_author VARCHAR(255) NULL;