-- Tags and trending activity support
CREATE TABLE IF NOT EXISTS tags (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  slug VARCHAR(64) NOT NULL UNIQUE,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_slug ON tags (slug);

CREATE TABLE IF NOT EXISTS snippet_tags (
  snippet_id BIGINT NOT NULL REFERENCES snippets(id) ON DELETE CASCADE,
  tag_id BIGINT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (snippet_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_snippet_tags_tag ON snippet_tags (tag_id);
CREATE INDEX IF NOT EXISTS idx_snippet_tags_snippet ON snippet_tags (snippet_id);

-- Materialized view summarising recent activity to surface trending snippets.
CREATE MATERIALIZED VIEW IF NOT EXISTS trending_snippet_activity AS
SELECT
    s.id AS snippet_id,
    COUNT(DISTINCT c.id) FILTER (WHERE c.created_utc >= NOW() - INTERVAL '7 days') AS recent_comment_count,
    COUNT(DISTINCT st.tag_id) AS tag_count,
    COALESCE(
      array_length(
        tsvector_to_array(
          to_tsvector('english', COALESCE(s.text_snippet, '') || ' ' || COALESCE(s.thoughts, ''))
        ),
        1
      ),
      0
    ) AS lexeme_count,
    MAX(s.created_utc) AS snippet_created_utc
FROM snippets s
LEFT JOIN comments c ON c.snippet_id = s.id
LEFT JOIN snippet_tags st ON st.snippet_id = s.id
GROUP BY s.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_trending_snippet_activity_id
  ON trending_snippet_activity (snippet_id);