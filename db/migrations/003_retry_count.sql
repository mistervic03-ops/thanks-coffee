ALTER TABLE recognition
    ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;

UPDATE recognition
SET retry_count = 0
WHERE feed_post_status = 'failed'
  AND retry_count IS NULL;
