import type { Metadata } from "next";

import {
  EmptyReadOnlyState,
  formatUtc,
  humanize,
  ReadOnlyPage,
  ReadOnlySection,
  shortId,
} from "@/components/demo/read-only-page";
import { Status } from "@/components/demo/status";
import type { Monitor } from "@/lib/histograph-api";
import { getMonitors } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Monitors — Histograph",
  description: "Read-only production ML monitor configuration and evaluation state.",
};

function monitorState(monitor: Monitor) {
  if (!monitor.enabled) return { label: "Disabled", tone: "neutral" as const };
  if (monitor.latest_run_triggered) return { label: "Threshold crossed", tone: "critical" as const };
  if (monitor.latest_run_status === "failed") {
    return { label: "Evaluation failed", tone: "critical" as const };
  }
  if (monitor.latest_run_status === "running") {
    return { label: "Evaluating", tone: "warning" as const };
  }
  if (monitor.latest_run_result_status === "insufficient_data") {
    return { label: "Awaiting evaluation", tone: "neutral" as const };
  }
  if (monitor.latest_run_status === "evaluated") {
    return { label: "Evaluated · no trigger", tone: "neutral" as const };
  }
  return { label: "Awaiting evaluation", tone: "neutral" as const };
}

function thresholdRule(monitor: Monitor) {
  const amount = `${(monitor.threshold * 100).toFixed(1)} pp`;
  if (monitor.operator === "decrease") return `Decrease ≥ ${amount}`;
  if (monitor.operator === "increase") return `Increase ≥ ${amount}`;
  if (monitor.operator === "change") return `Absolute change ≥ ${amount}`;
  if (monitor.metric === "psi") return `${monitor.operator} ${monitor.threshold.toFixed(3)}`;
  return `${humanize(monitor.operator)} ${(monitor.threshold * 100).toFixed(1)}%`;
}

function versionComparison(monitor: Monitor) {
  if (monitor.reference_version && monitor.version) {
    return `${monitor.reference_version} reference → ${monitor.version} candidate`;
  }
  return monitor.version ? `Version ${monitor.version}` : "Active deployment version";
}

export default async function MonitorsPage() {
  const monitors = await getMonitors();

  return (
    <ReadOnlyPage title="Monitors">
      <ReadOnlySection
        meta={
          <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
            {monitors.length} configured
          </span>
        }
        title="Monitor inventory"
      >
        {monitors.length === 0 ? (
          <EmptyReadOnlyState>No monitors have been configured.</EmptyReadOnlyState>
        ) : (
          monitors.map((monitor) => {
            const state = monitorState(monitor);

            return (
              <article
                className="scroll-mt-24 border-b border-white/7 px-5 py-5 last:border-b-0 target:bg-white/[0.025] sm:px-6"
                id={`monitor-${monitor.id}`}
                key={monitor.id}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-white/82">
                      {humanize(monitor.metric)} · {humanize(monitor.signal)}
                    </p>
                    <p className="mt-1 truncate font-mono text-[10px] text-white/28">
                      {shortId(monitor.id)} · {monitor.model}
                    </p>
                  </div>
                  <Status label={state.label} tone={state.tone} />
                </div>

                <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Versions</p>
                    <p className="mt-2 text-xs text-white/58">{versionComparison(monitor)}</p>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Alert rule</p>
                    <p className="mt-2 text-xs text-white/58">{thresholdRule(monitor)}</p>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Evaluation</p>
                    <p className="mt-2 text-xs text-white/58">
                      {monitor.evaluation_window_minutes
                        ? `${monitor.evaluation_window_minutes} min window`
                        : "Window not reported"}
                      {monitor.minimum_sample_size
                        ? ` · minimum ${monitor.minimum_sample_size} labeled outcomes`
                        : ""}
                    </p>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Last run</p>
                    <p className="mt-2 font-mono text-[10px] text-white/42">
                      {formatUtc(monitor.latest_run_at)}
                    </p>
                  </div>
                </div>
              </article>
            );
          })
        )}
      </ReadOnlySection>
    </ReadOnlyPage>
  );
}
