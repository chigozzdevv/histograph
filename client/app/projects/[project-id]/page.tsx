import Link from "next/link";

import { ProjectConfiguration } from "@/components/project-configuration";
import { ProjectOperations } from "@/components/project-operations";
import { StatusBadge } from "@/components/status-badge";
import {
  getAgentTargets,
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
  ]);
  const baselines = await getBaselines(projectId, questions);
  const githubInstallUrl = process.env.HISTOGRAPH_GITHUB_INSTALL_URL ?? null;
  const setupComplete =
    questions.length > 0 &&
    datahubConnections.some((connection) => connection.status === "ready") &&
    agentTargets.some((target) => target.status === "ready");
  const approvedQuestions = questions.filter(
    (question) => question.active_baseline_id,
  ).length;
  const lastRun = runs[0] ?? null;

  return (
    <main className="project-page">
      <Link className="back-link" href="/">
        ← Projects
      </Link>
      <section className="project-heading">
        <div>
          <h1>{project.name}</h1>
          <p className="environment-label">{project.environment}</p>
        </div>
      </section>

      {!setupComplete ? (
        <section className="setup-section">
          <ProjectConfiguration
            projectId={projectId}
            datahubConnections={datahubConnections}
            agentTargets={agentTargets}
            suites={suites}
            hasQuestions={false}
          />
        </section>
      ) : (
        <>
          <section className="overview-strip">
            <div>
              <strong>{questions.length}</strong>
              <span>checks</span>
            </div>
            <div>
              <strong>{approvedQuestions}</strong>
              <span>ready</span>
            </div>
            <div>
              <strong>
                {incidents.filter((item) => item.status === "open").length}
              </strong>
              <span>issues</span>
            </div>
            <div>
              <strong>{lastRun?.status.replaceAll("_", " ") ?? "Never"}</strong>
              <span>last run</span>
            </div>
          </section>

          <section className="page-section">
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

          {incidents.length ? (
            <section className="page-section compact-section">
              <div className="simple-section-title">
                <h2>Issues</h2>
              </div>
              <div className="activity-list">
                {incidents.slice(0, 8).map((incident) => (
                  <Link
                    className="activity-row"
                    href={`/projects/${projectId}/runs/${incident.latest_run_id}`}
                    key={incident.id}
                  >
                    <div>
                      <strong>{incident.title}</strong>
                      <span>{incident.summary}</span>
                    </div>
                    <span className={`incident-${incident.status}`}>
                      {incident.status}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {runs.length ? (
            <section className="page-section compact-section">
              <div className="simple-section-title">
                <h2>Recent runs</h2>
              </div>
              <div className="runs-table">
                {runs.map((run) => (
                  <Link
                    className="run-row"
                    href={`/projects/${projectId}/runs/${run.id}`}
                    key={run.id}
                  >
                    <div>
                      <strong>{run.trigger_type.replaceAll("_", " ")}</strong>
                      <span>
                        {run.report_json
                          ? `${run.report_json.passed} passed · ${run.report_json.failed} failed`
                          : "No results"}
                      </span>
                    </div>
                    <time>{new Date(run.queued_at).toLocaleString()}</time>
                    <StatusBadge status={run.status} />
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          <ProjectConfiguration
            projectId={projectId}
            datahubConnections={datahubConnections}
            agentTargets={agentTargets}
            suites={suites}
            hasQuestions
          />
        </>
      )}
    </main>
  );
}
