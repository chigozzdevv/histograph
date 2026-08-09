CREATE TABLE IF NOT EXISTS api_rate_limits (
    bucket TEXT NOT NULL,
    client_key TEXT NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL,
    PRIMARY KEY (bucket, client_key),
    CONSTRAINT api_rate_limits_count_check CHECK (request_count > 0)
);
