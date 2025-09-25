-- Direct messaging tables
CREATE TABLE IF NOT EXISTS dm_threads (
    id BIGSERIAL PRIMARY KEY,
    participant_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS dm_participants (
    thread_id BIGINT NOT NULL REFERENCES dm_threads(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_read_message_id BIGINT NULL,
    last_read_at TIMESTAMPTZ NULL,
    PRIMARY KEY (thread_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_dm_participants_user ON dm_participants (user_id);
CREATE INDEX IF NOT EXISTS idx_dm_participants_thread ON dm_participants (thread_id);

CREATE TABLE IF NOT EXISTS dm_messages (
    id BIGSERIAL PRIMARY KEY,
    thread_id BIGINT NOT NULL REFERENCES dm_threads(id) ON DELETE CASCADE,
    sender_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dm_messages_thread_created ON dm_messages (thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dm_messages_thread_id ON dm_messages (thread_id, id DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_dm_participants_last_read_message'
          AND table_name = 'dm_participants'
    ) THEN
        ALTER TABLE dm_participants
            ADD CONSTRAINT fk_dm_participants_last_read_message
            FOREIGN KEY (last_read_message_id)
            REFERENCES dm_messages(id)
            ON DELETE SET NULL;
    END IF;
END
$$;