CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    task TEXT NOT NULL,
    positive_class TEXT NOT NULL,
    positive_actual JSONB NOT NULL,
    datahub_urn TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deployments (
    id UUID PRIMARY KEY,
    deployment TEXT NOT NULL,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    strategy TEXT NOT NULL,
    traffic_percentage DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    endpoint TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS deployments_model_version_idx
    ON deployments (model, version, occurred_at DESC);

CREATE TABLE IF NOT EXISTS monitors (
    id UUID PRIMARY KEY,
    model TEXT NOT NULL,
    version TEXT,
    environment TEXT NOT NULL DEFAULT 'production',
    deployment TEXT,
    signal TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    baseline_window_minutes INTEGER NOT NULL,
    evaluation_window_minutes INTEGER NOT NULL,
    minimum_sample_size INTEGER NOT NULL DEFAULT 30,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS monitors_model_idx ON monitors (model, enabled);

ALTER TABLE monitors
    ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'production';
ALTER TABLE monitors
    ADD COLUMN IF NOT EXISTS deployment TEXT;
ALTER TABLE monitors
    ADD COLUMN IF NOT EXISTS minimum_sample_size INTEGER NOT NULL DEFAULT 30;

CREATE TABLE IF NOT EXISTS monitor_events (
    id UUID PRIMARY KEY,
    monitor_id UUID NOT NULL REFERENCES monitors(id),
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    signal TEXT NOT NULL,
    metric TEXT NOT NULL,
    observed_value DOUBLE PRECISION NOT NULL,
    baseline_value DOUBLE PRECISION,
    threshold DOUBLE PRECISION NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    affected_slice JSONB NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (monitor_id, occurred_at)
);

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    monitor_event_id UUID REFERENCES monitor_events(id),
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    signal TEXT NOT NULL,
    metric TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS incidents_model_idx ON incidents (model, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS incidents_monitor_event_unique_idx
    ON incidents (monitor_event_id) WHERE monitor_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS incident_events (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_events_incident_idx
    ON incident_events (incident_id, created_at);
