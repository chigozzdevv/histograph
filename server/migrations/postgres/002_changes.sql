CREATE TABLE IF NOT EXISTS changes (
    id UUID PRIMARY KEY,
    asset_urn TEXT NOT NULL,
    asset_name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    change_type TEXT NOT NULL,
    status TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS changes_environment_time_idx
    ON changes (environment, occurred_at DESC);

CREATE INDEX IF NOT EXISTS changes_asset_time_idx
    ON changes (asset_urn, occurred_at DESC);
