export type Organization = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export type Project = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  environment: "development" | "staging" | "production";
  timezone: string;
  retention_days: number;
  max_concurrent_runs: number;
  default_trigger_policy_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DataHubConnection = {
  id: string;
  name: string;
  mode: string;
  mcp_url: string;
  status: string;
  version: number;
  active: boolean;
  last_verified_at: string | null;
  last_error: string | null;
};

export type AgentTarget = {
  id: string;
  name: string;
  adapter_type: string;
  base_url: string;
  engine_name: string;
  status: string;
  version: number;
  active: boolean;
  last_verified_at: string | null;
  last_error: string | null;
};

export type TestSuite = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
};

export type Schedule = {
  id: string;
  name: string;
  cron_expression: string;
  timezone: string;
  concurrency_policy: string;
  active: boolean;
};

export type GitHubInstallation = {
  id: string;
  installation_id: number;
  account_login: string;
  account_type: string;
  repository_selection: string;
  permissions_json: Record<string, string>;
  suspended_at: string | null;
};

export type RepositoryConnection = {
  id: string;
  github_installation_id: string;
  repository_id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  configuration_json: Record<string, unknown>;
  active: boolean;
};

export type ProtectedQuestion = {
  id: string;
  suite_id: string;
  stable_key: string;
  name: string;
  description: string | null;
  criticality: string;
  owner_reference: string | null;
  active_version_id: string | null;
  active_baseline_id: string | null;
  active: boolean;
};

export type Baseline = {
  id: string;
  protected_question_id: string;
  test_version_id: string;
  source_execution_id: string | null;
  version: number;
  status: string;
  evidence_json: Record<string, unknown>;
  assertions_json: Record<string, unknown>;
  environment_fingerprint: string;
  approved_by: string | null;
  approved_at: string | null;
  approval_justification: string | null;
  created_at: string;
};

export type Incident = {
  id: string;
  protected_question_id: string;
  status: string;
  title: string;
  summary: string;
  resource_urn: string;
  first_run_id: string;
  latest_run_id: string;
  occurrence_count: number;
  consecutive_success_count: number;
  datahub_incident_urn: string | null;
  resolved_at: string | null;
  updated_at: string;
};

export type AuditEvent = {
  id: string;
  actor_type: string;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  request_id: string;
  details_json: Record<string, unknown>;
  created_at: string;
};

export type TestExecution = {
  id: string;
  protected_question_id: string;
  status: string;
  attempt_count: number;
  trace_id: string;
  evidence_json: Record<string, unknown> | null;
  evaluation_json: {
    status?: string;
    findings?: Array<{
      code: string;
      message: string;
      passed: boolean;
      level: string;
      evidence: Record<string, unknown>;
    }>;
  } | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type Run = {
  id: string;
  organization_id: string;
  project_id: string;
  trigger_type: string;
  trigger_reference: string | null;
  idempotency_key: string;
  requested_by: string;
  status: string;
  workflow_id: string | null;
  configuration_fingerprint: string;
  selection_json: Record<string, unknown>;
  impact_plan_json: {
    changed_asset_urns?: string[];
    selected_test_ids?: string[];
    excluded_test_ids?: string[];
    unknowns?: string[];
    risk_level?: string;
  } | null;
  report_json: {
    passed: number;
    failed: number;
    warnings: number;
    errors: number;
    status: string;
    baseline_draft_ids?: string[];
  } | null;
  error_code: string | null;
  error_message: string | null;
  queued_at: string;
  planned_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancellation_requested_at: string | null;
  superseded_by_run_id: string | null;
  created_at: string;
  updated_at: string;
};
