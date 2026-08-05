import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { getRun } from "@/lib/api-client";

type RunPageProps = {
  params: Promise<{ "run-id": string }>;
};

export default async function RunPage({ params }: RunPageProps) {
  const route = await params;
  const run = await getRun(route["run-id"]);
  const result = run.result;

  return (
    <main className="run-detail">
      <Link className="back-link" href="/">
        ← All runs
      </Link>
      <section className="run-heading">
        <div>
          <p className="eyebrow">Verification run</p>
          <h1>{run.test_case_name}</h1>
          <p className="run-id">{run.id}</p>
        </div>
        <StatusBadge status={run.status} />
      </section>

      {run.error ? <section className="error-panel">{run.error}</section> : null}

      {result ? (
        <>
          <section className="detail-grid">
            <article className="detail-card">
              <p className="eyebrow">DataHub context</p>
              <h2>{result.evidence.context.asset_urns.length} assets discovered</h2>
              <code>{result.evidence.context.query}</code>
              <ul className="asset-list">
                {result.evidence.context.asset_urns.map((urn) => (
                  <li key={urn}>{urn}</li>
                ))}
              </ul>
            </article>
            <article className="detail-card">
              <p className="eyebrow">Agent answer</p>
              <p className="answer">{result.evidence.final_response || "No final answer"}</p>
            </article>
          </section>

          <section className="detail-section">
            <div className="section-title">
              <div>
                <p className="eyebrow">Evaluation</p>
                <h2>{result.evaluation.findings.length} checks</h2>
              </div>
            </div>
            <div className="findings">
              {result.evaluation.findings.map((finding, index) => (
                <article className="finding" key={`${finding.code}-${index}`}>
                  <span className={finding.passed ? "finding-pass" : "finding-fail"}>
                    {finding.passed ? "Pass" : "Fail"}
                  </span>
                  <div>
                    <strong>{finding.message}</strong>
                    <code>{finding.code}</code>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="detail-section">
            <div className="section-title">
              <div>
                <p className="eyebrow">SQL evidence</p>
                <h2>{result.evidence.sql_executions.length} queries</h2>
              </div>
            </div>
            {result.evidence.sql_executions.map((execution, index) => (
              <article className="sql-panel" key={`${execution.sql}-${index}`}>
                <pre>{execution.sql}</pre>
                <p>
                  {execution.rows.length} rows · {execution.columns.join(", ")}
                </p>
              </article>
            ))}
          </section>
        </>
      ) : null}
    </main>
  );
}
