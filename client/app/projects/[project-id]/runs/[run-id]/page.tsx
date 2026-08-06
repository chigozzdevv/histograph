import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { getRun, getRunExecutions } from "@/lib/api-client";

type RunPageProps = {
  params: Promise<{ "project-id": string; "run-id": string }>;
};

export default async function RunPage({ params }: RunPageProps) {
  const route = await params;
  const projectId = route["project-id"];
  const [run, executions] = await Promise.all([
    getRun(projectId, route["run-id"]),
    getRunExecutions(projectId, route["run-id"]),
  ]);
  const plan = run.impact_plan_json;
  const report = run.report_json;

  return (
    <main className="run-detail">
      <Link className="back-link" href={`/projects/${projectId}`}>
        ← Project
      </Link>
      <section className="run-heading">
        <div>
          <p className="run-kicker">
            {run.trigger_type.replaceAll("_", " ")} run ·{" "}
            {new Date(run.queued_at).toLocaleString()}
          </p>
          <h1>Run results</h1>
        </div>
        <StatusBadge status={run.status} />
      </section>

      {run.error_message ? (
        <section className="error-panel">{run.error_message}</section>
      ) : null}

      <section className="result-summary">
        <div>
          <strong>
            {plan?.selected_test_ids?.length ?? executions.length}
          </strong>
          <span>questions checked</span>
        </div>
        <div>
          <strong>{report?.passed ?? 0}</strong>
          <span>passed</span>
        </div>
        <div>
          <strong>{report?.failed ?? 0}</strong>
          <span>failed</span>
        </div>
        <div>
          <strong>{report?.errors ?? 0}</strong>
          <span>errors</span>
        </div>
      </section>

      {plan?.unknowns?.length ? (
        <section className="attention-panel">
          <h2>Needs attention</h2>
          <ul>
            {plan.unknowns.map((unknown) => (
              <li key={unknown}>{unknown}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="page-section compact-section">
        <div className="simple-section-title">
          <h2>Checks</h2>
        </div>
        {executions.length ? (
          <div className="execution-list">
            {executions.map((execution, index) => (
              <article className="execution-card" key={execution.id}>
                <div className="execution-heading">
                  <h3>Check {index + 1}</h3>
                  <StatusBadge status={execution.status} />
                </div>
                {execution.error_message ? (
                  <p className="error-panel">{execution.error_message}</p>
                ) : null}
                <div className="findings">
                  {execution.evaluation_json?.findings?.map((finding) => (
                    <div
                      className="finding"
                      key={`${execution.id}-${finding.code}`}
                    >
                      <span
                        className={
                          finding.passed ? "finding-pass" : "finding-fail"
                        }
                      >
                        {finding.passed ? "Pass" : "Fail"}
                      </span>
                      <strong>{finding.message}</strong>
                    </div>
                  ))}
                </div>
                {execution.attempt_count > 1 ? (
                  <p className="attempt-note">
                    Completed after {execution.attempt_count} attempts.
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">No checks were run.</div>
        )}
      </section>
    </main>
  );
}
