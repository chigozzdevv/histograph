ALTER TABLE demo_runs
    DROP CONSTRAINT demo_runs_stage_check;

ALTER TABLE demo_runs
    ADD CONSTRAINT demo_runs_stage_check
    CHECK (
        stage IN (
            'queued', 'emitting_traffic', 'monitoring', 'investigating',
            'awaiting_approval', 'remediating', 'emitting_recovery_traffic',
            'verifying', 'resolved', 'failed'
        )
    );
