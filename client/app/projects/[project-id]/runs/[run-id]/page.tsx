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
      <Link className="back-link" href={`/projects/${projectId}`}>← Project</Link>
      <section className="run-heading">
        <div>
          <p className="eyebrow">{run.trigger_type.replaceAll("_", " ")} run</p>
          <h1>Behavioral assurance</h1>
          <p className="run-id">{run.id}</p>
        </div>
        <StatusBadge status={run.status} />
      </section>

      {run.error_message ? <section className="error-panel">{run.error_message}</section> : null}

      <section className="detail-grid">
        <article className="detail-card">
          <p className="eyebrow">Impact plan</p>
          <h2>{plan?.selected_test_ids?.length ?? 0} questions selected</h2>
          <p>Risk: <strong>{plan?.risk_level ?? "pending"}</strong></p>
          {plan?.changed_asset_urns?.length ? (
            <ul className="asset-list">{plan.changed_asset_urns.map((urn) => <li key={urn}>{urn}</li>)}</ul>
          ) : <p className="muted-copy">No metadata assets were supplied by this trigger.</p>}
        </article>
        <article className="detail-card">
          <p className="eyebrow">Evaluation</p>
          <h2>{report ? `${report.passed} passed · ${report.failed} failed` : "Waiting for evidence"}</h2>
          {report ? <p>{report.errors} infrastructure errors · {report.warnings} warnings</p> : null}
        </article>
      </section>

      {plan?.unknowns?.length ? (
        <section className="detail-section">
          <div className="section-title"><div><p className="eyebrow">Action required</p><h2>Unresolved context</h2></div></div>
          <div className="findings">{plan.unknowns.map((unknown) => <article className="finding" key={unknown}><span className="finding-fail">Review</span><strong>{unknown}</strong></article>)}</div>
        </section>
      ) : null}

      <section className="detail-section">
        <div className="section-title">
          <div><p className="eyebrow">Protected behavior</p><h2>Test executions</h2></div>
          <p>Every attempt is tied to immutable test, baseline, target and evidence references.</p>
        </div>
        {executions.length ? (
          <div className="execution-list">
            {executions.map((execution) => (
              <article className="execution-card" key={execution.id}>
                <div className="execution-heading">
                  <div><span className="run-id">{execution.protected_question_id}</span><h3>{execution.trace_id}</h3></div>
                  <StatusBadge status={execution.status} />
                </div>
                {execution.error_message ? <p className="error-panel">{execution.error_message}</p> : null}
                <div className="findings">
                  {execution.evaluation_json?.findings?.map((finding) => (
                    <div className="finding" key={`${execution.id}-${finding.code}`}>
                      <span className={finding.passed ? "finding-pass" : "finding-fail"}>
                        {finding.passed ? "Pass" : finding.level}
                      </span>
                      <div><strong>{finding.message}</strong><code>{finding.code}</code></div>
                    </div>
                  ))}
                </div>
                <dl className="execution-metadata">
                  <div><dt>Attempts</dt><dd>{execution.attempt_count}</dd></div>
                  <div><dt>Started</dt><dd>{execution.started_at ? new Date(execution.started_at).toLocaleString() : "Pending"}</dd></div>
                  <div><dt>Completed</dt><dd>{execution.completed_at ? new Date(execution.completed_at).toLocaleString() : "Pending"}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        ) : <div className="empty-state">No test execution evidence has been recorded yet.</div>}
      </section>
    </main>
  );
}
