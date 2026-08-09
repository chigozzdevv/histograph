ALTER TABLE gitops_deployments
    ADD COLUMN IF NOT EXISTS input_schema JSONB,
    ADD COLUMN IF NOT EXISTS output_schema JSONB,
    ADD COLUMN IF NOT EXISTS examples JSONB;

CREATE TABLE IF NOT EXISTS demo_runs (
    id UUID PRIMARY KEY,
    deployment_id UUID NOT NULL REFERENCES gitops_deployments(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    monitor_id UUID REFERENCES monitors(id),
    incident_id UUID REFERENCES incidents(id),
    action_id UUID REFERENCES remediation_actions(id),
    started_by TEXT NOT NULL,
    result JSONB,
    last_error TEXT,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT demo_runs_status_check
        CHECK (status IN ('queued', 'running', 'awaiting_approval', 'resolved', 'failed')),
    CONSTRAINT demo_runs_stage_check
        CHECK (
            stage IN (
                'queued', 'emitting_traffic', 'monitoring', 'investigating',
                'awaiting_approval', 'remediating', 'verifying', 'resolved', 'failed'
            )
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS demo_runs_one_active_idx
    ON demo_runs ((TRUE))
    WHERE status IN ('queued', 'running', 'awaiting_approval');

CREATE INDEX IF NOT EXISTS demo_runs_created_idx ON demo_runs (created_at DESC);
