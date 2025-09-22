-- Seed sample records that exercise group functionality for local development.
INSERT INTO users (username, password_hash, email, role)
VALUES
  ('demo_admin', 'local-dev-demo-hash', 'demo_admin@example.com', 'admin'),
  ('demo_member', 'local-dev-demo-hash', 'demo_member@example.com', 'user'),
  ('demo_moderator', 'local-dev-demo-hash', 'demo_moderator@example.com', 'moderator')
ON CONFLICT (username) DO UPDATE
SET
  password_hash = EXCLUDED.password_hash,
  email = EXCLUDED.email,
  role = EXCLUDED.role;

INSERT INTO groups (slug, name, description, privacy_state, created_by_user_id)
VALUES
  (
    'public-readers',
    'Public Readers Circle',
    'A welcoming group for sharing book highlights openly.',
    'public',
    (SELECT id FROM users WHERE username = 'demo_admin')
  ),
  (
    'private-study',
    'Private Study Circle',
    'Focused space for invite-only study notes and discussions.',
    'private',
    (SELECT id FROM users WHERE username = 'demo_admin')
  ),
  (
    'unlisted-historians',
    'Unlisted Historians',
    'A lightly hidden group for history buffs sharing drafts.',
    'unlisted',
    (SELECT id FROM users WHERE username = 'demo_moderator')
  )
ON CONFLICT (slug) DO UPDATE
SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  privacy_state = EXCLUDED.privacy_state,
  created_by_user_id = EXCLUDED.created_by_user_id;

-- Ensure group owners and members are present.
INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
SELECT g.id, u.id, 'owner', u.id
FROM groups g
JOIN users u ON u.username = 'demo_admin'
WHERE g.slug IN ('public-readers', 'private-study')
ON CONFLICT (group_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    added_by_user_id = EXCLUDED.added_by_user_id;

INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
SELECT g.id, u.id, 'member', (SELECT id FROM users WHERE username = 'demo_admin')
FROM groups g
JOIN users u ON u.username = 'demo_member'
WHERE g.slug IN ('public-readers', 'private-study')
ON CONFLICT (group_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    added_by_user_id = EXCLUDED.added_by_user_id;

INSERT INTO group_memberships (group_id, user_id, role, added_by_user_id)
SELECT g.id, u.id, 'moderator', u.id
FROM groups g
JOIN users u ON u.username = 'demo_moderator'
WHERE g.slug = 'unlisted-historians'
ON CONFLICT (group_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    added_by_user_id = EXCLUDED.added_by_user_id;

-- Create a sample invite into the private group.
INSERT INTO group_invites (
  group_id,
  invited_by_user_id,
  invited_user_email,
  invite_code,
  status,
  expires_utc
)
SELECT
  g.id,
  owner_members.user_id,
  'reader.one@example.com',
  'DEMO-PRIVATE-INVITE',
  'pending',
  NOW() + INTERVAL '30 days'
FROM groups g
JOIN group_memberships owner_members
  ON owner_members.group_id = g.id AND owner_members.role = 'owner'
WHERE g.slug = 'private-study'
ON CONFLICT (invite_code) DO UPDATE
SET
  group_id = EXCLUDED.group_id,
  invited_by_user_id = EXCLUDED.invited_by_user_id,
  invited_user_email = EXCLUDED.invited_user_email,
  status = EXCLUDED.status,
  expires_utc = EXCLUDED.expires_utc;

-- Create a couple of reusable tags.
INSERT INTO tags (name, slug)
VALUES
  ('Community Highlights', 'community-highlights'),
  ('Devotional Reading', 'devotional-reading')
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name;

-- Seed example snippets across public and private scopes.
WITH admin_user AS (
  SELECT id FROM users WHERE username = 'demo_admin'
),
public_group AS (
  SELECT id FROM groups WHERE slug = 'public-readers'
),
private_group AS (
  SELECT id FROM groups WHERE slug = 'private-study'
)
INSERT INTO snippets (
  date_read,
  book_name,
  chapter,
  verse,
  text_snippet,
  thoughts,
  created_by_user_id,
  group_id
)
SELECT
  CURRENT_DATE - INTERVAL '3 days',
  'The Open Library',
  'Introduction',
  '1',
  'Sharing our favorite passages keeps the stories alive.',
  'Posted in the public group so everyone can comment.',
  admin_user.id,
  public_group.id
FROM admin_user, public_group
WHERE NOT EXISTS (
  SELECT 1 FROM snippets s
  WHERE s.created_by_user_id = admin_user.id
    AND s.group_id = public_group.id
    AND s.text_snippet = 'Sharing our favorite passages keeps the stories alive.'
);

WITH admin_user AS (
  SELECT id FROM users WHERE username = 'demo_admin'
),
private_group AS (
  SELECT id FROM groups WHERE slug = 'private-study'
)
INSERT INTO snippets (
  date_read,
  book_name,
  chapter,
  verse,
  text_snippet,
  thoughts,
  created_by_user_id,
  group_id
)
SELECT
  CURRENT_DATE - INTERVAL '1 day',
  'Quiet Study Journal',
  'Chapter 3',
  '16',
  'Private reflections help our group stay focused.',
  'Only members of the private study circle should see this.',
  admin_user.id,
  private_group.id
FROM admin_user, private_group
WHERE NOT EXISTS (
  SELECT 1 FROM snippets s
  WHERE s.created_by_user_id = admin_user.id
    AND s.group_id = private_group.id
    AND s.text_snippet = 'Private reflections help our group stay focused.'
);

WITH admin_user AS (
  SELECT id FROM users WHERE username = 'demo_admin'
)
INSERT INTO snippets (
  date_read,
  book_name,
  chapter,
  verse,
  text_snippet,
  thoughts,
  created_by_user_id,
  group_id
)
SELECT
  CURRENT_DATE - INTERVAL '10 days',
  'Solo Reading Notes',
  'Appendix',
  '4',
  'This standalone snippet is visible to the whole library.',
  'Global snippets remain group_id NULL for open discovery.',
  admin_user.id,
  NULL
FROM admin_user
WHERE NOT EXISTS (
  SELECT 1 FROM snippets s
  WHERE s.created_by_user_id = admin_user.id
    AND s.group_id IS NULL
    AND s.text_snippet = 'This standalone snippet is visible to the whole library.'
);

-- Attach tags to snippets within their visibility scopes.
WITH tag_data AS (
  SELECT id, slug FROM tags WHERE slug IN ('community-highlights', 'devotional-reading')
),
public_snippet AS (
  SELECT id FROM snippets
  WHERE text_snippet = 'Sharing our favorite passages keeps the stories alive.'
),
private_snippet AS (
  SELECT id, group_id FROM snippets
  WHERE text_snippet = 'Private reflections help our group stay focused.'
)
INSERT INTO snippet_tags (snippet_id, tag_id)
SELECT ps.id, td.id
FROM public_snippet ps
JOIN tag_data td ON td.slug = 'community-highlights'
WHERE NOT EXISTS (
  SELECT 1 FROM snippet_tags st
  WHERE st.snippet_id = ps.id AND st.tag_id = td.id
);

WITH private_snippet AS (
  SELECT id, group_id FROM snippets
  WHERE text_snippet = 'Private reflections help our group stay focused.'
),
private_tag AS (
  SELECT id FROM tags WHERE slug = 'devotional-reading'
)
INSERT INTO group_snippet_tags (group_id, snippet_id, tag_id)
SELECT ps.group_id, ps.id, pt.id
FROM private_snippet ps, private_tag pt
WHERE ps.group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM group_snippet_tags gst
    WHERE gst.group_id = ps.group_id
      AND gst.snippet_id = ps.id
      AND gst.tag_id = pt.id
  );

-- Demonstrate comments scoped to a private group snippet.
WITH private_snippet AS (
  SELECT id, group_id FROM snippets
  WHERE text_snippet = 'Private reflections help our group stay focused.'
),
commenter AS (
  SELECT id FROM users WHERE username = 'demo_member'
)
INSERT INTO comments (snippet_id, user_id, content, group_id)
SELECT ps.id, commenter.id, 'Excited to keep these notes within our circle!', ps.group_id
FROM private_snippet ps, commenter
WHERE NOT EXISTS (
  SELECT 1 FROM comments c
  WHERE c.snippet_id = ps.id
    AND c.user_id = commenter.id
    AND c.content = 'Excited to keep these notes within our circle!'
);

-- Refresh the trending materialized view so seeded snippets appear immediately.
REFRESH MATERIALIZED VIEW trending_snippet_activity;