-- Notifications tables and preferences
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_type') THEN
        CREATE TYPE notification_type AS ENUM (
            'reply_to_snippet',
            'reply_to_comment',
            'mention',
            'vote_on_your_snippet',
            'moderation_update',
            'system'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_email_digest') THEN
        CREATE TYPE notification_email_digest AS ENUM (
            'off',
            'daily',
            'weekly'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type notification_type NOT NULL,
    actor_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    snippet_id BIGINT NULL REFERENCES snippets(id) ON DELETE SET NULL,
    comment_id BIGINT NULL REFERENCES comments(id) ON DELETE SET NULL,
    title TEXT NULL,
    body TEXT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_read_created
    ON notifications (user_id, is_read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON notifications (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    reply_to_snippet BOOLEAN NOT NULL DEFAULT TRUE,
    reply_to_comment BOOLEAN NOT NULL DEFAULT TRUE,
    mention BOOLEAN NOT NULL DEFAULT TRUE,
    vote_on_your_snippet BOOLEAN NOT NULL DEFAULT TRUE,
    moderation_update BOOLEAN NOT NULL DEFAULT TRUE,
    system BOOLEAN NOT NULL DEFAULT TRUE,
    email_digest notification_email_digest NOT NULL DEFAULT 'weekly',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notification_prefs_email_digest
    ON notification_prefs (email_digest);
