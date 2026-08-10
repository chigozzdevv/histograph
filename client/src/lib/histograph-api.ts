import "server-only";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonObject = { [key: string]: JsonValue };

export type OverviewResponse = {
  counts: {
    deployments: number;
    active_monitors: number;
    active_incidents: number;
    pending_approvals: number;
    github_connections: number;
  };
  latest_incident: Incident | null;
  latest_demo_run: {
    id: string;
    deployment_id: string;
    status: string;
    stage: string;
    monitor_id: string | null;
    incident_id: string | null;
    action_id: string | null;
    created_at: string;
    updated_at: string;
    finished_at: string | null;
    last_error: string | null;
  } | null;
};

export type Deployment = {
  id: string;
  deployment: string;
  model: string;
  environment: string;
  provider: string;
  datahub_model_urn: string;
  desired_revision: string;
  manifest: {
    metadata: { name: string };
    spec: {
      environment: string;
      model: {
        name: string;
        task?: string;
        positiveClass?: string;
        positiveActual?: JsonValue;
        datahubModelUrn: string;
      };
      runtime?: { provider: string; endpoint?: string };
      stable: {
        version: string;
        trafficPercentage: number;
        artifact?: string;
        configuration?: Record<string, JsonValue>;
      };
      candidate?: {
        version: string;
        trafficPercentage: number;
        artifact?: string;
        configuration?: Record<string, JsonValue>;
      };
      features: Array<{
        name: string;
        version: string;
        assetUrn: string;
        inputFeature?: string;
        configuration?: Record<string, JsonValue>;
      }>;
    };
  };
  observed_state: {
    model_versions?: Record<
      string,
      {
        version: string;
        traffic_percentage: number;
        status: string;
      }
    >;
    features?: Record<
      string,
      {
        status: string;
        version: string;
        asset_name: string;
        asset_urn: string;
        change_type: string;
      }
    >;
  } | null;
  observed_at: string | null;
  sync_status: "desired_only" | "in_sync" | "out_of_sync";
  input_schema?: JsonObject | null;
  output_schema?: JsonObject | null;
  examples?: Array<{
    id?: string;
    label?: string;
    input: JsonObject;
    expectedActual?: JsonValue;
  }> | null;
  repository_owner?: string;
  repository_name?: string;
  branch?: string;
  manifest_path?: string;
  created_at: string;
  updated_at: string;
};

export type Incident = {
  id: string;
  monitor_id?: string | null;
  monitor_event_id?: string | null;
  model: string;
  version: string;
  signal?: string;
  metric?: string;
  status: "open" | "investigating" | "resolved" | "closed";
  severity: string;
  summary: string;
  evidence?: Record<string, JsonValue>;
  created_at: string;
  resolved_at: string | null;
};

export type Monitor = {
  id: string;
  model: string;
  version: string | null;
  environment: string;
  deployment: string | null;
  signal: string;
  metric: string;
  reference_version: string | null;
  operator: string;
  threshold: number;
  baseline_window_minutes?: number;
  evaluation_window_minutes?: number;
  minimum_sample_size?: number;
  check_interval_seconds?: number;
  enabled: boolean;
  latest_run_status: string | null;
  latest_run_result_status: string | null;
  latest_run_triggered: boolean | null;
  latest_run_at: string | null;
};

export type MonitorRun = {
  id: string;
  monitor_id: string;
  status: string;
  triggered: boolean | null;
  result: {
    status?: string;
    observed_value?: number | null;
    baseline_value?: number | null;
    threshold?: number | null;
    sample_size?: number | null;
    incident_id?: string | null;
  } | null;
  started_at: string;
  finished_at: string | null;
};

export type IncidentTimelineEvent = {
  id: string;
  incident_id: string;
  event_type: string;
  details: JsonObject;
  created_at: string;
};

export type IncidentDetail = Incident & {
  timeline: IncidentTimelineEvent[];
};

export type RemediationAction = {
  id: string;
  incident_id: string;
  action_type: string;
  status: string;
  adapter: string;
  target: JsonObject;
  evidence: JsonObject;
  proposed_at: string;
  approved_at: string | null;
  execution_started_at: string | null;
  execution_completed_at: string | null;
  external_execution_id: string | null;
};

export type PredictionResult = {
  prediction_id: string;
  model: string;
  version: string;
  deployment: string;
  score: number;
  predicted_class: string;
  threshold: number;
  observed_at: string;
};

export type ComparisonResult = {
  stable: PredictionResult;
  candidate: PredictionResult;
  telemetry_recorded: false;
};

export type ActivityItem = {
  id: string;
  category: "deployment" | "change" | "incident" | "remediation";
  event_type: string;
  entity_id: string;
  details: Record<string, JsonValue>;
  created_at: string;
};

export type Integrations = {
  github: {
    configured: boolean;
    connections: Array<{
      id: string;
      repository_owner: string;
      repository_name: string;
      enabled: boolean;
      last_error: string | null;
    }>;
  };
  datahub: {
    configured: boolean;
    write_back_enabled: boolean;
  };
  reference_runtime: {
    control_configured: boolean;
    allowed_hosts: string[];
  };
};

export type DashboardData = {
  overview: OverviewResponse;
  deployments: Deployment[];
  incidents: Incident[];
  monitors: Monitor[];
  monitorRuns: MonitorRun[];
  activity: ActivityItem[];
  integrations: Integrations;
};

const apiBase = (
  process.env.HISTOGRAPH_API_URL ??
  process.env.NEXT_PUBLIC_HISTOGRAPH_API_URL ??
  "https://histograph.ai"
).replace(/\/$/, "");

class HistographApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "HistographApiError";
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(8000),
  });

  if (!response.ok) {
    throw new HistographApiError(
      response.status,
      `Histograph API returned ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

async function mutate<T>(path: string, body: JsonObject): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(12_000),
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Histograph API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getDashboardData(): Promise<DashboardData> {
  const [overview, deployments, incidents, monitors, activity, integrations] =
    await Promise.all([
      request<OverviewResponse>("/v1/overview"),
      request<Deployment[]>("/v1/deployments"),
      request<Incident[]>("/v1/incidents?limit=20"),
      request<Monitor[]>("/v1/monitors?limit=20"),
      request<ActivityItem[]>("/v1/activity?limit=12"),
      request<Integrations>("/v1/integrations"),
    ]);

  const activeIncident = incidents.find((incident) =>
    ["open", "investigating"].includes(incident.status),
  );
  const selectedMonitor =
    monitors.find((monitor) => monitor.id === activeIncident?.monitor_id) ?? monitors[0];
  const monitorRuns = selectedMonitor
    ? await request<MonitorRun[]>(`/v1/monitors/${selectedMonitor.id}/runs?limit=12`)
    : [];

  return {
    overview,
    deployments,
    incidents,
    monitors,
    monitorRuns,
    activity,
    integrations,
  };
}

export async function getDeployments(): Promise<Deployment[]> {
  return request<Deployment[]>("/v1/deployments");
}

export async function getDeployment(deploymentId: string): Promise<Deployment | null> {
  try {
    return await request<Deployment>(`/v1/deployments/${deploymentId}`);
  } catch (error) {
    if (error instanceof HistographApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getIncidents(): Promise<Incident[]> {
  return request<Incident[]>("/v1/incidents?limit=100");
}

export async function getIncident(incidentId: string): Promise<IncidentDetail | null> {
  try {
    return await request<IncidentDetail>(`/v1/incidents/${incidentId}`);
  } catch (error) {
    if (error instanceof HistographApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getIncidentActions(incidentId: string): Promise<RemediationAction[]> {
  return request<RemediationAction[]>(`/v1/incidents/${incidentId}/actions`);
}

export async function getMonitors(): Promise<Monitor[]> {
  return request<Monitor[]>("/v1/monitors?limit=100");
}

export async function getMonitorRuns(monitorId: string, limit = 20): Promise<MonitorRun[]> {
  return request<MonitorRun[]>(`/v1/monitors/${monitorId}/runs?limit=${limit}`);
}

export async function getActivity(): Promise<ActivityItem[]> {
  return request<ActivityItem[]>("/v1/activity?limit=100");
}

export async function getIntegrations(): Promise<Integrations> {
  return request<Integrations>("/v1/integrations");
}

export async function runPlayground(
  deploymentId: string,
  mode: "compare" | "predict",
  input: JsonObject,
): Promise<ComparisonResult | PredictionResult> {
  return mutate<ComparisonResult | PredictionResult>(
    `/v1/deployments/${deploymentId}/${mode}`,
    { input },
  );
}
