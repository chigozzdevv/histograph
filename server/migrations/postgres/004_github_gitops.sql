ALTER TABLE remediation_action_events
    ADD COLUMN IF NOT EXISTS sequence BIGINT GENERATED ALWAYS AS IDENTITY;

CREATE UNIQUE INDEX IF NOT EXISTS remediation_action_events_sequence_idx
    ON remediation_action_events (sequence);

CREATE TABLE IF NOT EXISTS github_connections (
    id UUID PRIMARY KEY,
    installation_id BIGINT NOT NULL,
    repository_owner TEXT NOT NULL,
    repository_name TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'main',
    manifest_path TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository_owner, repository_name, branch, manifest_path)
);

CREATE TABLE IF NOT EXISTS gitops_deployments (
    id UUID PRIMARY KEY,
    connection_id UUID NOT NULL REFERENCES github_connections(id) ON DELETE CASCADE,
    deployment TEXT NOT NULL,
    model TEXT NOT NULL,
    environment TEXT NOT NULL,
    provider TEXT NOT NULL,
    datahub_model_urn TEXT NOT NULL,
    desired_revision TEXT NOT NULL,
    manifest_sha TEXT NOT NULL,
    manifest_content TEXT NOT NULL,
    manifest JSONB NOT NULL,
    observed_state JSONB,
    observed_at TIMESTAMPTZ,
    sync_status TEXT NOT NULL DEFAULT 'desired_only',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT gitops_deployments_sync_status_check
        CHECK (sync_status IN ('desired_only', 'in_sync', 'out_of_sync')),
    UNIQUE (connection_id, deployment, environment)
);

CREATE INDEX IF NOT EXISTS gitops_deployments_target_idx
    ON gitops_deployments (model, deployment, environment);

CREATE TABLE IF NOT EXISTS gitops_pull_requests (
    action_id UUID PRIMARY KEY REFERENCES remediation_actions(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES github_connections(id) ON DELETE CASCADE,
    deployment_id UUID NOT NULL REFERENCES gitops_deployments(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    head_branch TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    pull_request_number BIGINT,
    pull_request_url TEXT,
    merge_sha TEXT,
    approved_by TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    merged_at TIMESTAMPTZ,
    CONSTRAINT gitops_pull_requests_status_check
        CHECK (status IN ('creating', 'open', 'merged', 'closed', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS gitops_pull_requests_repository_number_idx
    ON gitops_pull_requests (connection_id, pull_request_number)
    WHERE pull_request_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS github_webhook_deliveries (
    delivery_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT github_webhook_deliveries_status_check
        CHECK (status IN ('processing', 'completed', 'failed'))
);
