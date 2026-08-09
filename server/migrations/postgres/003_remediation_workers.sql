ALTER TABLE monitors
    ADD COLUMN IF NOT EXISTS feature TEXT,
    ADD COLUMN IF NOT EXISTS reference_version TEXT,
    ADD COLUMN IF NOT EXISTS check_interval_seconds INTEGER NOT NULL DEFAULT 60,
    ADD COLUMN IF NOT EXISTS next_evaluation_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS last_evaluated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_owner TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE monitors
    ADD CONSTRAINT monitors_check_interval_seconds_check
    CHECK (check_interval_seconds BETWEEN 5 AND 86400);

UPDATE monitors
SET enabled = FALSE,
    last_error = 'Feature target must be configured before continuous evaluation is enabled'
WHERE signal = 'feature_drift' AND feature IS NULL;

CREATE INDEX IF NOT EXISTS monitors_due_idx
    ON monitors (next_evaluation_at)
    WHERE enabled = TRUE;

CREATE TABLE IF NOT EXISTS monitor_runs (
    id UUID PRIMARY KEY,
    monitor_id UUID NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    worker_id TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    triggered BOOLEAN,
    result JSONB,
    error TEXT,
    CONSTRAINT monitor_runs_status_check
        CHECK (status IN ('running', 'evaluated', 'failed')),
    UNIQUE (monitor_id, scheduled_for)
);

CREATE INDEX IF NOT EXISTS monitor_runs_monitor_idx
    ON monitor_runs (monitor_id, started_at DESC);

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS monitor_id UUID REFERENCES monitors(id),
    ADD COLUMN IF NOT EXISTS investigation_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS investigation_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS investigation_next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS investigation_lease_owner TEXT,
    ADD COLUMN IF NOT EXISTS investigation_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS investigation_last_error TEXT;

ALTER TABLE incidents
    ADD CONSTRAINT incidents_investigation_status_check
    CHECK (investigation_status IN ('pending', 'running', 'completed', 'failed'));

UPDATE incidents AS incidents
SET monitor_id = monitor_events.monitor_id
FROM monitor_events
WHERE incidents.monitor_event_id = monitor_events.id
  AND incidents.monitor_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS incidents_active_monitor_unique_idx
    ON incidents (monitor_id)
    WHERE monitor_id IS NOT NULL AND status IN ('open', 'investigating');

CREATE INDEX IF NOT EXISTS incidents_investigation_due_idx
    ON incidents (investigation_next_attempt_at)
    WHERE investigation_status IN ('pending', 'failed');

CREATE TABLE IF NOT EXISTS remediation_actions (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    adapter TEXT NOT NULL,
    target JSONB NOT NULL,
    evidence JSONB NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    execution_started_at TIMESTAMPTZ,
    execution_finished_at TIMESTAMPTZ,
    external_execution_id TEXT,
    execution_result JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    next_verification_at TIMESTAMPTZ,
    recovery_verified_at TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT remediation_actions_type_check
        CHECK (action_type IN ('stop_canary', 'rollback_model', 'rollback_release')),
    CONSTRAINT remediation_actions_status_check
        CHECK (
            status IN (
                'proposed', 'approved', 'rejected', 'executing',
                'succeeded', 'failed', 'cancelled'
            )
        ),
    CONSTRAINT remediation_actions_recovery_check
        CHECK (recovery_verified_at IS NULL OR status = 'succeeded')
);

CREATE INDEX IF NOT EXISTS remediation_actions_incident_idx
    ON remediation_actions (incident_id, proposed_at DESC);

CREATE INDEX IF NOT EXISTS remediation_actions_execution_due_idx
    ON remediation_actions (approved_at)
    WHERE status = 'approved';

CREATE INDEX IF NOT EXISTS remediation_actions_recovery_due_idx
    ON remediation_actions (next_verification_at)
    WHERE status = 'succeeded' AND recovery_verified_at IS NULL;

CREATE TABLE IF NOT EXISTS remediation_approvals (
    id UUID PRIMARY KEY,
    action_id UUID NOT NULL UNIQUE REFERENCES remediation_actions(id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT remediation_approvals_decision_check
        CHECK (decision IN ('approve', 'reject')),
    CONSTRAINT remediation_approvals_rejection_reason_check
        CHECK (decision <> 'reject' OR reason IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS remediation_action_events (
    id UUID PRIMARY KEY,
    action_id UUID NOT NULL REFERENCES remediation_actions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS remediation_action_events_action_idx
    ON remediation_action_events (action_id, created_at, id);
