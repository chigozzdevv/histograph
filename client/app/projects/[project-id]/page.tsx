import Link from "next/link";

import { ProjectConfiguration } from "@/components/project-configuration";
import { ProjectOperations } from "@/components/project-operations";
import { StatusBadge } from "@/components/status-badge";
import {
  getAgentTargets,
  getAuditEvents,
  getBaselines,
  getDataHubConnections,
  getGitHubInstallations,
  getIncidents,
  getProject,
  getProtectedQuestions,
  getRepositories,
  getRuns,
  getSchedules,
  getTestSuites,
} from "@/lib/api-client";

type ProjectPageProps = {
  params: Promise<{ "project-id": string }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { "project-id": projectId } = await params;
  const project = await getProject(projectId);
  const [
    datahubConnections,
    agentTargets,
    suites,
    schedules,
    runs,
    githubInstallations,
    repositories,
    questions,
    incidents,
    auditEvents,
  ] = await Promise.all([
    getDataHubConnections(projectId),
    getAgentTargets(projectId),
    getTestSuites(projectId),
    getSchedules(projectId),
    getRuns(projectId),
    getGitHubInstallations(project.organization_id),
    getRepositories(projectId),
    getProtectedQuestions(projectId),
    getIncidents(projectId),
    getAuditEvents(projectId),
  ]);
  const baselines = await getBaselines(projectId, questions);
  const githubInstallUrl = process.env.HISTOGRAPH_GITHUB_INSTALL_URL ?? null;

  return (
    <main className="project-page">
      <Link className="back-link" href="/">← All projects</Link>
      <section className="project-heading">
        <div>
          <p className="eyebrow">{project.environment} assurance project</p>
          <h1>{project.name}</h1>
          <p>{project.timezone} · {project.retention_days}-day evidence retention</p>
        </div>
        <div className="project-metrics">
          <span><strong>{suites.length}</strong> suites</span>
          <span><strong>{questions.length}</strong> questions</span>
          <span><strong>{schedules.length}</strong> schedules</span>
          <span><strong>{incidents.filter((item) => item.status === "open").length}</strong> open incidents</span>
        </div>
      </section>

      <section className="content-section">
        <div className="section-title">
          <div><p className="eyebrow">Automation</p><h2>Gates, baselines and schedules</h2></div>
          <p>GitHub and Temporal trigger the same durable workflow used by manual and metadata runs.</p>
        </div>
        <ProjectOperations
          projectId={projectId}
          organizationId={project.organization_id}
          githubInstallUrl={githubInstallUrl}
          githubInstallations={githubInstallations}
          repositories={repositories}
          suites={suites}
          questions={questions}
          baselines={baselines}
          schedules={schedules}
          timezone={project.timezone}
        />
      </section>

      <section className="content-section">
        <div className="section-title">
          <div><p className="eyebrow">Configuration</p><h2>Execution boundary</h2></div>
          <p>Credentials stay server-side and are encrypted before PostgreSQL persistence.</p>
        </div>
        <ProjectConfiguration
          projectId={projectId}
          datahubConnections={datahubConnections}
          agentTargets={agentTargets}
          suites={suites}
        />
      </section>

      <section className="content-section operations-grid">
        <div>
          <div className="section-title compact-title">
            <div><p className="eyebrow">Live regressions</p><h2>Incidents</h2></div>
          </div>
          {incidents.length ? (
            <div className="activity-list">
              {incidents.slice(0, 8).map((incident) => (
                <Link className="activity-row" href={`/projects/${projectId}/runs/${incident.latest_run_id}`} key={incident.id}>
                  <div><strong>{incident.title}</strong><span>{incident.resource_urn}</span></div>
                  <span className={`incident-${incident.status}`}>{incident.status}</span>
                </Link>
              ))}
            </div>
          ) : <div className="empty-state">No live regressions have opened incidents.</div>}
        </div>
        <div>
          <div className="section-title compact-title">
            <div><p className="eyebrow">Accountability</p><h2>Audit trail</h2></div>
          </div>
          {auditEvents.length ? (
            <div className="activity-list">
              {auditEvents.slice(0, 8).map((event) => (
                <div className="activity-row" key={event.id}>
                  <div><strong>{event.action.replaceAll("_", " ")}</strong><span>{event.actor_id}</span></div>
                  <time>{new Date(event.created_at).toLocaleString()}</time>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">No project changes have been recorded.</div>}
        </div>
      </section>

      <section className="content-section">
        <div className="section-title">
          <div><p className="eyebrow">Evidence</p><h2>Recent runs</h2></div>
        </div>
        {runs.length ? (
          <div className="runs-table">
            {runs.map((run) => (
              <Link className="run-row" href={`/projects/${projectId}/runs/${run.id}`} key={run.id}>
                <div><strong>{run.trigger_type.replaceAll("_", " ")}</strong><span>{run.id}</span></div>
                <time>{new Date(run.queued_at).toLocaleString()}</time>
                <StatusBadge status={run.status} />
              </Link>
            ))}
          </div>
        ) : <div className="empty-state">No assurance runs have been queued.</div>}
      </section>
    </main>
  );
}
