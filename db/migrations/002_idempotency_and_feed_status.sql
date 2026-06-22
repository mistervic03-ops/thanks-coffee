ALTER TABLE recognition
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS feed_post_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS feed_posted_at TIMESTAMPTZ;

UPDATE recognition
SET feed_post_status = 'posted'
WHERE feed_message_ts IS NOT NULL
  AND feed_post_status = 'pending';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'recognition_idempotency_key_unique'
    ) THEN
        ALTER TABLE recognition
            ADD CONSTRAINT recognition_idempotency_key_unique UNIQUE (idempotency_key);
    END IF;
END $$;
