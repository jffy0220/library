-- Recreate the trending materialized view to respect group privacy states.
DROP MATERIALIZED VIEW IF EXISTS trending_snippet_activity;

CREATE MATERIALIZED VIEW trending_snippet_activity AS
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
LEFT JOIN groups g ON g.id = s.group_id
WHERE s.group_id IS NULL OR g.privacy_state = 'public'
GROUP BY s.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_trending_snippet_activity_id
  ON trending_snippet_activity (snippet_id);