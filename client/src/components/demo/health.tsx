import { Status } from "@/components/demo/status";
import type { Incident, JsonValue, Monitor, MonitorRun } from "@/lib/histograph-api";

function percent(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function points(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)} pp` : "—";
}

function triggerValue(evidence: Record<string, JsonValue> | undefined, key: string) {
  const trigger = evidence?.trigger;
  if (!trigger || typeof trigger !== "object" || Array.isArray(trigger)) return undefined;
  const value = trigger[key];
  return typeof value === "number" ? value : undefined;
}

function MetricComparison({
  stable,
  candidate,
  boundary,
  stableVersion,
  candidateVersion,
}: {
  stable?: number;
  candidate?: number;
  boundary?: number;
  stableVersion: string;
  candidateVersion: string;
}) {
  if (typeof stable !== "number" || typeof candidate !== "number") {
    return (
      <div className="dashboard-chart-grid flex min-h-46 items-center justify-center border-t border-white/8">
        <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
          Awaiting first evaluation
        </span>
      </div>
    );
  }

  const stableWidth = `${Math.max(0, Math.min(1, stable)) * 100}%`;
  const candidateWidth = `${Math.max(0, Math.min(1, candidate)) * 100}%`;
  const boundaryPosition = `${Math.max(0, Math.min(1, boundary ?? 0)) * 100}%`;

  return (
    <div className="dashboard-chart-grid border-t border-white/8 px-5 py-6 sm:px-6 sm:py-7">
      <div className="grid grid-cols-[5.75rem_minmax(0,1fr)_3.5rem] items-center gap-x-3 gap-y-6 pt-5 sm:grid-cols-[7rem_minmax(0,1fr)_4rem]">
        <span className="font-mono text-[10px] text-white/42">Stable · {stableVersion}</span>
        <div className="relative h-3 border border-white/8 bg-white/[0.025]">
          <span
            aria-hidden="true"
            className="absolute inset-y-0 left-0 bg-critical/[0.045]"
            style={{ width: boundaryPosition }}
          />
          <span
            aria-hidden="true"
            className="absolute inset-y-0 left-0 bg-white/52"
            style={{ width: stableWidth }}
          />
          {typeof boundary === "number" ? (
            <span
              aria-hidden="true"
              className="absolute -top-5 bottom-[-1.9rem] z-10 border-l border-dashed border-critical/65"
              style={{ left: boundaryPosition }}
            >
              <span className="absolute -top-0.5 left-2 whitespace-nowrap font-mono text-[9px] tracking-[0.08em] text-critical/68 uppercase">
                boundary {percent(boundary)}
              </span>
            </span>
          ) : null}
        </div>
        <span className="text-right font-mono text-[10px] text-white/58">{percent(stable)}</span>

        <span className="font-mono text-[10px] text-white/42">
          Candidate · {candidateVersion}
        </span>
        <div className="relative h-3 border border-white/8 bg-white/[0.025]">
          <span
            aria-hidden="true"
            className="absolute inset-y-0 left-0 bg-critical/[0.045]"
            style={{ width: boundaryPosition }}
          />
          <span
            aria-hidden="true"
            className="absolute inset-y-0 left-0 bg-brand-soft"
            style={{ width: candidateWidth }}
          />
          {candidate === 0 ? (
            <span className="absolute top-1/2 left-0 size-2 -translate-y-1/2 border border-brand-soft bg-[#0a0a0a]" />
          ) : null}
        </div>
        <span className="text-right font-mono text-[10px] text-brand-soft">
          {percent(candidate)}
        </span>

        <span aria-hidden="true" />
        <div className="flex justify-between font-mono text-[9px] text-white/20">
          <span>0%</span>
          <span>25%</span>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}

function monitorState(
  monitor: Monitor | undefined,
  run: MonitorRun | undefined,
  incident: Incident | null,
) {
  if (incident && ["open", "investigating"].includes(incident.status)) {
    return { label: "Incident open", tone: "critical" as const };
  }
  if (incident?.status === "resolved" && incident.evidence?.recovery) {
    return { label: "Recovery verified", tone: "success" as const };
  }
  if (run?.status === "insufficient_data" || run?.result?.status === "insufficient_data") {
    return { label: "Awaiting labeled outcomes", tone: "neutral" as const };
  }
  if (run?.triggered) return { label: "Threshold crossed", tone: "critical" as const };
  if (run?.status === "evaluated" || run?.result?.status === "evaluated") {
    return { label: "Within allowed decrease", tone: "success" as const };
  }
  return { label: monitor?.enabled ? "Monitoring" : "Inactive", tone: "neutral" as const };
}

export function Health({
  monitor,
  runs,
  incident,
}: {
  monitor: Monitor | undefined;
  runs: MonitorRun[];
  incident: Incident | null;
}) {
  const evaluatedRun =
    runs.find(
      (run) =>
        (run.status === "evaluated" || run.result?.status === "evaluated") &&
        typeof run.result?.baseline_value === "number" &&
        typeof run.result?.observed_value === "number",
    ) ??
    runs.find(
      (run) =>
        typeof run.result?.baseline_value === "number" &&
        typeof run.result?.observed_value === "number",
    ) ??
    runs[0];
  const incidentIsActive = incident && ["open", "investigating"].includes(incident.status);
  const incidentObserved = triggerValue(incident?.evidence, "observed_value");
  const incidentBaseline = triggerValue(incident?.evidence, "baseline_value");
  const observed =
    (incidentIsActive ? incidentObserved : undefined) ?? evaluatedRun?.result?.observed_value ?? undefined;
  const baseline =
    (incidentIsActive ? incidentBaseline : undefined) ?? evaluatedRun?.result?.baseline_value ?? undefined;
  const decrease =
    typeof baseline === "number" && typeof observed === "number"
      ? Math.max(0, baseline - observed)
      : undefined;
  const boundary =
    typeof baseline === "number" && monitor?.operator === "decrease"
      ? Math.max(0, baseline - monitor.threshold)
      : undefined;
  const state = monitorState(monitor, evaluatedRun, incident);

  return (
    <section className="min-w-0 bg-[#0a0a0a]" id="monitors">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">
          Canary {monitor?.metric.replaceAll("_", " ") ?? "performance"}
        </h2>
        <Status label={state.label} tone={state.tone} />
      </div>

      <div className="grid grid-cols-2 border-t border-white/8 sm:grid-cols-4">
        <div className="px-5 py-5 sm:px-6">
          <p className="font-mono text-[9px] tracking-[0.12em] text-white/30 uppercase">
            Stable · {monitor?.reference_version ?? "reference"}
          </p>
          <p className="mt-3 text-2xl tracking-[-0.045em] text-white/76">
            {percent(baseline)}
          </p>
        </div>
        <div className="border-l border-white/8 px-5 py-5 sm:px-6">
          <p className="font-mono text-[9px] tracking-[0.12em] text-white/30 uppercase">
            Candidate · {monitor?.version ?? "active"}
          </p>
          <p className="mt-3 text-2xl tracking-[-0.045em] text-white">
            {percent(observed)}
          </p>
        </div>
        <div className="border-t border-white/8 px-5 py-5 sm:border-t-0 sm:border-l sm:px-6">
          <p className="font-mono text-[9px] tracking-[0.12em] text-white/30 uppercase">
            Decrease
          </p>
          <p className="mt-3 text-2xl tracking-[-0.045em] text-critical/88">
            {points(decrease)}
          </p>
        </div>
        <div className="border-t border-l border-white/8 px-5 py-5 sm:border-t-0 sm:px-6">
          <p className="font-mono text-[9px] tracking-[0.12em] text-white/30 uppercase">
            Alert rule
          </p>
          <p className="mt-3 text-2xl tracking-[-0.045em] text-white/68">
            ≥ {points(monitor?.threshold)}
          </p>
        </div>
      </div>

      <MetricComparison
        boundary={boundary}
        candidate={observed}
        candidateVersion={monitor?.version ?? "candidate"}
        stable={baseline}
        stableVersion={monitor?.reference_version ?? "stable"}
      />

      <div className="flex min-h-10 items-center justify-between border-t border-white/8 px-5 font-mono text-[9px] text-white/25 sm:px-6">
        <span>
          {typeof monitor?.evaluation_window_minutes === "number"
            ? `${monitor.evaluation_window_minutes} min window`
            : "—"}
        </span>
        <span>
          {typeof monitor?.minimum_sample_size === "number"
            ? `Minimum ${monitor.minimum_sample_size} labeled outcomes`
            : "—"}
        </span>
      </div>
    </section>
  );
}
