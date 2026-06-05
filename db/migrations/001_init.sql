CREATE TABLE IF NOT EXISTS recognition (
    id                SERIAL PRIMARY KEY,
    sender_id         TEXT NOT NULL,
    receiver_id       TEXT NOT NULL,
    message           TEXT NOT NULL,
    unit_count        INT NOT NULL DEFAULT 1,
    source_channel_id TEXT,
    feed_channel_id   TEXT,
    feed_message_ts   TEXT,
    tags              TEXT[] DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recognition_sender_created
    ON recognition (sender_id, created_at);

CREATE INDEX IF NOT EXISTS idx_recognition_receiver_created
    ON recognition (receiver_id, created_at);
