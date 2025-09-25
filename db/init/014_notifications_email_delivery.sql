-- Add support for tracking emailed notifications for digest delivery
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS emailed_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_user_unemailed
    ON notifications (user_id, created_at DESC)
    WHERE emailed_at IS NULL AND is_read = FALSE;