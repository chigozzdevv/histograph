import "server-only";

import type {
  AgentTarget,
  AuditEvent,
  Baseline,
  DataHubConnection,
  GitHubInstallation,
  Incident,
  Organization,
  Project,
  ProtectedQuestion,
  RepositoryConnection,
  Run,
  Schedule,
  TestSuite,
  TestExecution,
} from "@/lib/types";

const apiUrl = process.env.HISTOGRAPH_API_URL ?? "http://localhost:8000";

async function apiRequest<T>(path: string): Promise<T> {
  const token = process.env.HISTOGRAPH_API_TOKEN;
  if (!token) {
    throw new Error("HISTOGRAPH_API_TOKEN is not configured");
  }
  const response = await fetch(`${apiUrl}/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Histograph API request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getOrganizations(): Promise<Organization[]> {
  return apiRequest("/organizations");
}

export function getProjects(organizationId: string): Promise<Project[]> {
  return apiRequest(`/projects?organization_id=${encodeURIComponent(organizationId)}`);
}

export function getProject(projectId: string): Promise<Project> {
  return apiRequest(`/projects/${projectId}`);
}

export function getDataHubConnections(projectId: string): Promise<DataHubConnection[]> {
  return apiRequest(`/projects/${projectId}/datahub-connections`);
}

export function getAgentTargets(projectId: string): Promise<AgentTarget[]> {
  return apiRequest(`/projects/${projectId}/agent-targets`);
}

export function getTestSuites(projectId: string): Promise<TestSuite[]> {
  return apiRequest(`/projects/${projectId}/test-suites`);
}

export function getSchedules(projectId: string): Promise<Schedule[]> {
  return apiRequest(`/projects/${projectId}/schedules`);
}

export function getGitHubInstallations(organizationId: string): Promise<GitHubInstallation[]> {
  return apiRequest(`/organizations/${organizationId}/github-installations`);
}

export function getRepositories(projectId: string): Promise<RepositoryConnection[]> {
  return apiRequest(`/projects/${projectId}/repositories`);
}

export function getProtectedQuestions(projectId: string): Promise<ProtectedQuestion[]> {
  return apiRequest(`/projects/${projectId}/protected-questions`);
}

export async function getBaselines(
  projectId: string,
  questions: ProtectedQuestion[],
): Promise<Baseline[]> {
  const groups = await Promise.all(
    questions.map((question) =>
      apiRequest<Baseline[]>(`/projects/${projectId}/protected-questions/${question.id}/baselines`),
    ),
  );
  return groups.flat();
}

export function getIncidents(projectId: string): Promise<Incident[]> {
  return apiRequest(`/projects/${projectId}/incidents`);
}

export function getAuditEvents(projectId: string): Promise<AuditEvent[]> {
  return apiRequest(`/projects/${projectId}/audit-events?limit=25`);
}

export async function getRuns(projectId: string): Promise<Run[]> {
  const payload = await apiRequest<{ items: Run[] }>(`/projects/${projectId}/runs`);
  return payload.items;
}

export function getRun(projectId: string, runId: string): Promise<Run> {
  return apiRequest(`/projects/${projectId}/runs/${runId}`);
}

export function getRunExecutions(projectId: string, runId: string): Promise<TestExecution[]> {
  return apiRequest(`/projects/${projectId}/runs/${runId}/executions`);
}
