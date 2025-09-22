-- Support collaborative snippet sharing via user groups.
CREATE TABLE IF NOT EXISTS groups (
  id BIGSERIAL PRIMARY KEY,
  slug VARCHAR(80) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT NULL,
  privacy_state TEXT NOT NULL DEFAULT 'public' CHECK (privacy_state IN ('public', 'private', 'unlisted')),
  created_by_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_slug ON groups(slug);
CREATE INDEX IF NOT EXISTS idx_groups_privacy ON groups(privacy_state);
CREATE INDEX IF NOT EXISTS idx_groups_slug_privacy ON groups(slug, privacy_state);

CREATE TABLE IF NOT EXISTS group_memberships (
  group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'moderator', 'member')),
  joined_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  added_by_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_memberships_user ON group_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_group_memberships_group_role ON group_memberships(group_id, role);

CREATE TABLE IF NOT EXISTS group_invites (
  id BIGSERIAL PRIMARY KEY,
  group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  invited_by_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invited_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
  invited_user_email TEXT NULL,
  invite_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'revoked', 'expired')),
  expires_utc TIMESTAMPTZ NULL,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  accepted_utc TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_group_invites_code ON group_invites(invite_code);
CREATE INDEX IF NOT EXISTS idx_group_invites_group_status ON group_invites(group_id, status);
CREATE INDEX IF NOT EXISTS idx_group_invites_email_lower
  ON group_invites((LOWER(invited_user_email)))
  WHERE invited_user_email IS NOT NULL;

ALTER TABLE snippets
  ADD COLUMN IF NOT EXISTS group_id BIGINT NULL REFERENCES groups(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_snippets_group ON snippets(group_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_snippets_id_group ON snippets(id, group_id);

ALTER TABLE comments
  ADD COLUMN IF NOT EXISTS group_id BIGINT NULL REFERENCES groups(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_comments_group ON comments(group_id);

ALTER TABLE comments
  ADD CONSTRAINT fk_comments_snippet_group
    FOREIGN KEY (snippet_id, group_id)
    REFERENCES snippets(id, group_id);

UPDATE comments c
SET group_id = s.group_id
FROM snippets s
WHERE c.snippet_id = s.id
  AND (c.group_id IS DISTINCT FROM s.group_id);

CREATE OR REPLACE FUNCTION ensure_comment_group_privacy()
RETURNS TRIGGER AS $$
DECLARE
  snippet_group BIGINT;
BEGIN
  SELECT group_id INTO snippet_group FROM snippets WHERE id = NEW.snippet_id;

  IF snippet_group IS NULL THEN
    IF NEW.group_id IS NOT NULL THEN
      RAISE EXCEPTION 'Public snippets cannot have group-scoped comments';
    END IF;
    NEW.group_id := NULL;
  ELSE
    IF NEW.group_id IS NULL THEN
      NEW.group_id := snippet_group;
    ELSIF NEW.group_id <> snippet_group THEN
      RAISE EXCEPTION 'Comment group_id % must match snippet group_id %', NEW.group_id, snippet_group;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_comments_group_privacy ON comments;
CREATE TRIGGER trg_comments_group_privacy
  BEFORE INSERT OR UPDATE ON comments
  FOR EACH ROW
  EXECUTE FUNCTION ensure_comment_group_privacy();

CREATE TABLE IF NOT EXISTS group_snippet_tags (
  group_id BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  snippet_id BIGINT NOT NULL REFERENCES snippets(id) ON DELETE CASCADE,
  tag_id BIGINT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (group_id, snippet_id, tag_id),
  FOREIGN KEY (snippet_id, group_id) REFERENCES snippets(id, group_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_group_snippet_tags_tag ON group_snippet_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_group_snippet_tags_snippet ON group_snippet_tags(snippet_id);
CREATE INDEX IF NOT EXISTS idx_group_snippet_tags_group ON group_snippet_tags(group_id);

ALTER TABLE content_flags
  ADD COLUMN IF NOT EXISTS group_id BIGINT NULL REFERENCES groups(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_content_flags_group ON content_flags(group_id);

WITH flag_groups AS (
  SELECT
    cf.id,
    CASE
      WHEN cf.content_type = 'snippet' THEN s.group_id
      WHEN cf.content_type = 'comment' THEN c.group_id
      ELSE NULL
    END AS group_id
  FROM content_flags cf
  LEFT JOIN snippets s ON s.id = cf.content_id AND cf.content_type = 'snippet'
  LEFT JOIN comments c ON c.id = cf.content_id AND cf.content_type = 'comment'
)
UPDATE content_flags cf
SET group_id = fg.group_id
FROM flag_groups fg
WHERE cf.id = fg.id
  AND (cf.group_id IS DISTINCT FROM fg.group_id);

CREATE OR REPLACE FUNCTION sync_content_flag_group()
RETURNS TRIGGER AS $$
DECLARE
  target_group BIGINT;
BEGIN
  IF NEW.content_type = 'snippet' THEN
    SELECT group_id INTO target_group FROM snippets WHERE id = NEW.content_id;
  ELSIF NEW.content_type = 'comment' THEN
    SELECT group_id INTO target_group FROM comments WHERE id = NEW.content_id;
  ELSE
    target_group := NULL;
  END IF;

  IF target_group IS NULL THEN
    NEW.group_id := NULL;
  ELSE
    NEW.group_id := target_group;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_content_flags_group_sync ON content_flags;
CREATE TRIGGER trg_content_flags_group_sync
  BEFORE INSERT OR UPDATE ON content_flags
  FOR EACH ROW
  EXECUTE FUNCTION sync_content_flag_group();