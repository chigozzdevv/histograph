"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import {
  resetControlledScenario,
  type ResetScenarioActionState,
} from "@/app/demo/scenarios/actions";
import { ArrowUpRightIcon } from "@/components/demo/icons";
import {
  formatUtc,
  humanize,
  ReadOnlySection,
  shortId,
} from "@/components/demo/read-only-page";
import { Status } from "@/components/demo/status";
import type {
  DemoScenarioSnapshot,
  DemoScenarioTraffic,
  Deployment,
  JsonObject,
  JsonValue,
} from "@/lib/histograph-api";

const resetInitialState: ResetScenarioActionState = { status: "idle" };
const terminalStatuses = new Set(["resolved", "failed"]);

function asObject(value: JsonValue | undefined): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function asString(value: JsonValue | undefined) {
  return typeof value === "string" ? value : null;
}

function runState(status: string, stage: string) {
  if (status === "resolved") return { label: "Resolved", tone: "success" as const };
  if (status === "failed") return { label: "Failed", tone: "critical" as const };
  if (stage === "awaiting_approval") {
    return { label: "Awaiting approval", tone: "warning" as const };
  }
  return { label: humanize(stage), tone: "neutral" as const };
}

function count(value: number | undefined) {
  return typeof value === "number" ? value.toLocaleString("en-US") : "—";
}

function percent(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function trafficSummary(traffic: DemoScenarioTraffic | undefined, deployment: Deployment | null) {
  const counts = traffic?.routing_counts;
  if (!counts) return "Waiting for runtime traffic";

  const stable = deployment?.manifest.spec.stable.version;
  const candidate = deployment?.manifest.spec.candidate?.version;
  const versions = [stable, candidate, ...Object.keys(counts)].filter(
    (version): version is string => typeof version === "string",
  );
  const ordered = versions.filter(
    (version, index) => versions.indexOf(version) === index && version in counts,
  );
  const outcomes = traffic.outcome_count ?? Object.values(counts).reduce((sum, value) => sum + value, 0);
  return `${ordered.map((version) => `${version} ${count(counts[version])}`).join(" · ")} · outcomes ${count(outcomes)}`;
}

function EvidenceLink({
  external,
  href,
  label,
}: {
  external?: boolean;
  href?: string | null;
  label: string;
}) {
  if (!href) return null;
  const className =
    "inline-flex items-center gap-1.5 text-xs text-white/48 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";

  return external ? (
    <a className={className} href={href} rel="noopener noreferrer" target="_blank">
      {label}
      <ArrowUpRightIcon className="size-3.5" />
    </a>
  ) : (
    <Link className={className} href={href}>
      {label}
      <ArrowUpRightIcon className="size-3.5" />
    </Link>
  );
}

function JourneyStep({
  label,
  meta,
  status,
  tone = "neutral",
  href,
  linkLabel,
  external,
  first = false,
  last = false,
}: {
  label: string;
  meta: string;
  status: string;
  tone?: "neutral" | "success" | "warning" | "critical";
  href?: string | null;
  linkLabel?: string;
  external?: boolean;
  first?: boolean;
  last?: boolean;
}) {
  const pending = status === "Pending";
  const indicators = {
    neutral: "border-white/30 bg-white/36",
    success: "border-success bg-success",
    warning: "border-brand-soft bg-brand-soft",
    critical: "border-critical bg-critical",
  };

  return (
    <div className="relative grid grid-cols-[1rem_minmax(0,1fr)] gap-4 px-5 sm:px-6">
      <span
        aria-hidden="true"
        className={`absolute left-7 w-px bg-white/12 sm:left-8 ${first ? "top-7" : "top-0"} ${last ? "bottom-7" : "bottom-0"}`}
      />
      <span
        aria-hidden="true"
        className={`relative z-10 mt-6 size-2.5 justify-self-center border ${pending ? "border-white/20 bg-[#0a0a0a]" : indicators[tone]}`}
      />
      <div
        className={`grid min-w-0 gap-3 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center ${last ? "" : "border-b border-white/7"}`}
      >
        <div className="min-w-0">
          <p className="text-sm font-medium text-white/76">{label}</p>
          <p className="mt-1 truncate font-mono text-[10px] text-white/30">{meta}</p>
        </div>
        <div className="flex items-center justify-between gap-5 sm:justify-end">
          <EvidenceLink external={external} href={href} label={linkLabel ?? "View"} />
          <Status label={status} tone={tone} />
        </div>
      </div>
    </div>
  );
}

export function ScenarioRun({ initialSnapshot }: { initialSnapshot: DemoScenarioSnapshot }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [pollError, setPollError] = useState(false);
  const [resetState, resetAction, resetPending] = useActionState(
    resetControlledScenario,
    resetInitialState,
  );
  const { run, deployment, monitor, monitor_run: monitorRun, incident, action } = snapshot;

  useEffect(() => {
    if (terminalStatuses.has(snapshot.run.status)) return;

    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await fetch(`/api/demo/scenarios/${snapshot.run.id}`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Scenario refresh failed");
        const next = (await response.json()) as DemoScenarioSnapshot;
        if (!cancelled) {
          setSnapshot(next);
          setPollError(false);
        }
      } catch {
        if (!cancelled) setPollError(true);
      }
    };
    const timer = window.setInterval(refresh, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [snapshot.run.id, snapshot.run.status]);

  const state = runState(run.status, run.stage);
  const traffic = run.result.traffic;
  const recoveryTraffic = run.result.recovery_traffic;
  const trigger = monitorRun?.triggered === true || Boolean(incident);
  const reference = monitorRun?.result?.baseline_value;
  const candidate = monitorRun?.result?.observed_value;
  const investigation = asObject(incident?.evidence?.investigation);
  const datahub = asObject(incident?.evidence?.datahub);
  const rootCause = asString(incident?.evidence?.root_cause_status);
  const datahubStatus = asString(datahub?.status);
  const pullRequest = action?.pull_request;
  const reset = resetState.status === "success" ? resetState.reset : run.result.reset;
  const monitorMeta =
    typeof reference === "number" && typeof candidate === "number"
      ? `${monitor?.reference_version ?? "stable"} ${percent(reference)} · ${monitor?.version ?? "candidate"} ${percent(candidate)}`
      : monitor
        ? `${monitor.reference_version ?? "stable"} → ${monitor.version ?? "candidate"} · ${humanize(monitor.metric)}`
        : "Waiting for the monitor record";

  return (
    <div className="mt-7 space-y-5">
      <ReadOnlySection meta={<Status label={state.label} tone={state.tone} />} title="Scenario journey">
        <JourneyStep
          first
          href={deployment ? `/demo/deployments/${deployment.id}` : null}
          label="Traffic replay"
          linkLabel="Deployment"
          meta={trafficSummary(traffic, deployment)}
          status={traffic ? "Complete" : run.stage === "emitting_traffic" ? "Running" : "Pending"}
          tone={traffic ? "success" : "neutral"}
        />
        <JourneyStep
          href={run.monitor_id ? `/demo/monitors#monitor-${run.monitor_id}` : null}
          label="Performance monitor"
          linkLabel="Monitor"
          meta={monitorMeta}
          status={trigger ? "Triggered" : monitor ? "Evaluating" : "Pending"}
          tone={trigger ? "critical" : "neutral"}
        />
        <JourneyStep
          href={incident ? `/demo/incidents/${incident.id}` : null}
          label="Investigation"
          linkLabel="Incident"
          meta={rootCause ? humanize(rootCause) : investigation ? "DataHub context collected" : "Waiting for incident investigation"}
          status={incident ? humanize(incident.status) : "Pending"}
          tone={incident ? (incident.status === "resolved" ? "success" : "warning") : "neutral"}
        />
        <JourneyStep
          external
          href={pullRequest?.pull_request_url}
          label="Rollback pull request"
          linkLabel="Review PR"
          meta={
            pullRequest?.pull_request_number
              ? `#${pullRequest.pull_request_number}${pullRequest.approved_by ? ` · merged by ${pullRequest.approved_by}` : ""}`
              : action
                ? `Action ${shortId(action.id)}`
                : "Waiting for confirmed evidence"
          }
          status={pullRequest ? humanize(pullRequest.status) : action ? humanize(action.status) : "Pending"}
          tone={pullRequest?.status === "merged" ? "success" : action ? "warning" : "neutral"}
        />
        <JourneyStep
          href={deployment ? `/demo/deployments/${deployment.id}` : null}
          label="Recovery traffic"
          linkLabel="Deployment"
          meta={trafficSummary(recoveryTraffic, deployment)}
          status={recoveryTraffic ? "Complete" : ["emitting_recovery_traffic", "verifying"].includes(run.stage) ? humanize(run.stage) : "Pending"}
          tone={recoveryTraffic ? "success" : "neutral"}
        />
        <JourneyStep
          external
          href={deployment?.source_links?.datahub}
          label="DataHub evidence"
          linkLabel="Open DataHub"
          meta={datahubStatus ? humanize(datahubStatus) : deployment?.datahub_model_urn ?? "Waiting for investigation"}
          status={datahubStatus === "written_back" ? "Written back" : datahubStatus ? "Investigated" : "Pending"}
          tone={datahubStatus === "written_back" ? "success" : "neutral"}
        />
        <JourneyStep
          last
          href={incident ? `/demo/incidents/${incident.id}` : null}
          label="Resolution"
          linkLabel="Incident"
          meta={action?.recovery_verified_at ? `Verified ${formatUtc(action.recovery_verified_at)}` : "Fresh healthy evidence required"}
          status={run.status === "resolved" ? "Verified" : "Pending"}
          tone={run.status === "resolved" ? "success" : "neutral"}
        />
        {pollError || run.last_error ? (
          <p className="border-t border-white/7 px-5 py-3 text-xs text-critical sm:px-6" role="alert">
            {run.last_error ?? "Live refresh interrupted. Retrying…"}
          </p>
        ) : null}
      </ReadOnlySection>

      {terminalStatuses.has(run.status) ? (
        <ReadOnlySection
          meta={
            reset ? (
              <EvidenceLink external href={reset.pull_request_url} label="Review reset PR" />
            ) : null
          }
          title="Reset"
        >
          <form action={resetAction} className="flex items-center justify-between gap-5 px-5 py-5 sm:px-6">
            <input name="runId" type="hidden" value={run.id} />
            <span aria-live="polite" className="text-xs text-critical" role="alert">
              {resetState.status === "error" ? resetState.message : ""}
            </span>
            <button
              className="ml-auto inline-flex h-10 items-center justify-center border border-white/14 px-4 text-sm text-white/68 transition-colors hover:border-white/28 hover:text-white disabled:cursor-not-allowed disabled:text-white/24"
              disabled={Boolean(reset) || resetPending}
              type="submit"
            >
              {reset ? "Reset PR open" : resetPending ? "Opening…" : "Reset demo"}
            </button>
          </form>
        </ReadOnlySection>
      ) : null}
    </div>
  );
}
