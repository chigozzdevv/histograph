import Link from "next/link";

import { RunForm } from "@/components/run-form";
import { StatusBadge } from "@/components/status-badge";
import { getRuns } from "@/lib/api-client";

export default async function HomePage() {
  let runs: Awaited<ReturnType<typeof getRuns>> = [];
  let unavailable = false;
  try {
    runs = await getRuns();
  } catch {
    unavailable = true;
  }

  return (
    <main>
      <section className="hero">
        <p className="eyebrow">Continuous assurance for data agents</p>
        <h1>Know when context changes the answer.</h1>
        <p className="hero-copy">
          Histograph uses DataHub lineage and business context to rerun affected analytics-agent
          behaviour, evaluate the evidence, and stop silent regressions.
        </p>
        <div className="flow-strip">
          <span>Change detected</span>
          <i />
          <span>DataHub impact</span>
          <i />
          <span>Agent executed</span>
          <i />
          <span>Evidence evaluated</span>
        </div>
      </section>

      <section className="content-section">
        <div className="section-title">
          <div>
            <p className="eyebrow">Execute</p>
            <h2>Run an agent test</h2>
          </div>
          <p>Every hard result is decided by deterministic evidence, not another model’s opinion.</p>
        </div>
        <RunForm />
      </section>

      <section className="content-section runs-section">
        <div className="section-title">
          <div>
            <p className="eyebrow">Evidence</p>
            <h2>Recent runs</h2>
          </div>
        </div>
        {unavailable ? (
          <div className="empty-state">The Histograph API is unavailable.</div>
        ) : runs.length === 0 ? (
          <div className="empty-state">No verification runs have been recorded yet.</div>
        ) : (
          <div className="runs-table">
            {runs.map((run) => (
              <Link className="run-row" href={`/runs/${run.id}`} key={run.id}>
                <div>
                  <strong>{run.test_case_name}</strong>
                  <span>{run.test_case_id}</span>
                </div>
                <time>{new Date(run.started_at).toLocaleString()}</time>
                <StatusBadge status={run.status} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
