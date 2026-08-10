import type { Metadata } from "next";
import Link from "next/link";

import { ArrowUpRightIcon } from "@/components/demo/icons";
import {
  EmptyReadOnlyState,
  formatUtc,
  humanize,
  ReadOnlyPage,
  ReadOnlySection,
  shortId,
} from "@/components/demo/read-only-page";
import { Status } from "@/components/demo/status";
import type {
  IncidentDetail,
  JsonObject,
  JsonValue,
  RemediationAction,
  RemediationActionDetail,
} from "@/lib/histograph-api";
import { getAction, getIncident, getIncidentActions } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Incident — Histograph",
  description: "Persisted incident evidence, timeline, and remediation state.",
};

function asObject(value: JsonValue | undefined): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function asString(value: JsonValue | undefined) {
  return typeof value === "string" ? value : null;
}

function asNumber(value: JsonValue | undefined) {
  return typeof value === "number" ? value : null;
}

function metricValue(metric: string | undefined, value: number | null) {
  if (value === null) return "—";
  return metric === "psi" ? value.toFixed(3) : `${(value * 100).toFixed(1)}%`;
}

function incidentStatus(status: IncidentDetail["status"]) {
  if (status === "resolved") return { label: "Resolved", tone: "success" as const };
  if (status === "closed") return { label: "Closed", tone: "neutral" as const };
  if (status === "investigating") return { label: "Investigating", tone: "warning" as const };
  return { label: "Open", tone: "critical" as const };
}

function actionStatus(action: RemediationAction) {
  if (action.status === "succeeded") return { label: "Execution succeeded", tone: "success" as const };
  if (["failed", "rejected"].includes(action.status)) {
    return { label: humanize(action.status), tone: "critical" as const };
  }
  if (["proposed", "approved", "executing"].includes(action.status)) {
    return { label: humanize(action.status), tone: "warning" as const };
  }
  return { label: humanize(action.status), tone: "neutral" as const };
}

function primitiveEntries(value: JsonObject) {
  return Object.entries(value).filter((entry): entry is [string, string | number | boolean] =>
    ["string", "number", "boolean"].includes(typeof entry[1]),
  );
}

function EvidenceSummary({ incident }: { incident: IncidentDetail }) {
  const evidence = incident.evidence;
  const trigger = asObject(evidence?.trigger);
  const detection = asObject(evidence?.detection);
  const datahub = asObject(evidence?.datahub);
  const recovery = asObject(evidence?.recovery);
  const rootCauseStatus = asString(evidence?.root_cause_status);
  const comparisonType = asString(detection?.comparison_type);
  const reference = asObject(detection?.reference);
  const candidate = asObject(detection?.candidate);
  const isCanary = comparisonType === "candidate_against_reference_version";
  const baseline = asNumber(trigger?.baseline_value);
  const observed = asNumber(trigger?.observed_value);
  const threshold = asNumber(trigger?.threshold);
  const referenceVersion = asString(reference?.version);
  const candidateVersion = asString(candidate?.version) ?? incident.version;

  return (
    <div className="grid sm:grid-cols-2 xl:grid-cols-4">
      <div className="px-5 py-5 sm:px-6">
        <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
          {isCanary ? `Reference ${referenceVersion ?? "version"}` : "Baseline"}
        </p>
        <p className="mt-2 text-lg text-white/76">{metricValue(incident.metric, baseline)}</p>
      </div>
      <div className="border-t border-white/7 px-5 py-5 sm:border-t-0 sm:border-l sm:px-6">
        <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
          {isCanary ? `Candidate ${candidateVersion}` : "Observed"}
        </p>
        <p className="mt-2 text-lg text-white/88">{metricValue(incident.metric, observed)}</p>
      </div>
      <div className="border-t border-white/7 px-5 py-5 sm:border-l sm:px-6 xl:border-t-0">
        <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
          {isCanary ? "Allowed decrease" : "Threshold"}
        </p>
        <p className="mt-2 text-lg text-white/68">
          {threshold === null
            ? "—"
            : isCanary
              ? `${(threshold * 100).toFixed(1)} pp`
              : metricValue(incident.metric, threshold)}
        </p>
      </div>
      <div className="border-t border-white/7 px-5 py-5 sm:border-l sm:px-6 xl:border-t-0">
        <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
          Investigation
        </p>
        <p className="mt-2 text-sm text-white/68">
          {rootCauseStatus ? humanize(rootCauseStatus) : "Not recorded"}
        </p>
        <p className="mt-1 font-mono text-[10px] text-white/28">
          DataHub: {humanize(asString(datahub?.status) ?? "not recorded")}
          {recovery ? ` · Recovery: ${humanize(asString(recovery.status) ?? "recorded")}` : ""}
        </p>
      </div>
    </div>
  );
}

export default async function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [incident, recordedActions] = await Promise.all([getIncident(id), getIncidentActions(id)]);
  const actions = (
    await Promise.all(recordedActions.map((action) => getAction(action.id)))
  ).filter((action): action is RemediationActionDetail => action !== null);

  if (!incident) {
    return (
      <ReadOnlyPage description="The requested record could not be loaded or does not exist." title="Incident unavailable">
        <ReadOnlySection title="Incident record">
          <EmptyReadOnlyState>
            Return to the incident list and select an available persisted record.
          </EmptyReadOnlyState>
        </ReadOnlySection>
      </ReadOnlyPage>
    );
  }

  const status = incidentStatus(incident.status);
  const repeatedSignals = incident.timeline.filter(
    (event) => event.event_type === "signal_repeated",
  );
  const timeline = [
    ...incident.timeline.filter((event) => event.event_type !== "signal_repeated"),
    ...(repeatedSignals.length > 0
      ? [
          {
            ...repeatedSignals[repeatedSignals.length - 1],
            id: `${incident.id}-repeated-signals`,
          },
        ]
      : []),
  ].sort((left, right) => left.created_at.localeCompare(right.created_at));

  return (
    <ReadOnlyPage
      action={
        <Link
          className="text-sm text-white/46 transition-colors hover:text-white/78 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          href="/demo/incidents"
        >
          Back to incidents
        </Link>
      }
      description={`${shortId(incident.id)} · ${incident.model} · ${incident.version}`}
      title={`${humanize(incident.metric ?? incident.signal ?? "Model")} degradation`}
    >
      <ReadOnlySection meta={<Status label={status.label} tone={status.tone} />} title="Summary">
        <div className="px-5 py-6 sm:px-6">
          <p className="max-w-4xl text-lg leading-7 tracking-[-0.02em] text-white/82">
            {incident.summary}
          </p>
          <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Signal", incident.signal ? humanize(incident.signal) : "—"],
              ["Metric", incident.metric ? humanize(incident.metric) : "—"],
              ["Severity", humanize(incident.severity)],
              ["Created", formatUtc(incident.created_at)],
            ].map(([label, value]) => (
              <div key={label}>
                <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">{label}</p>
                <p className="mt-2 text-sm text-white/62">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </ReadOnlySection>

      <ReadOnlySection title="Detection and investigation evidence">
        <EvidenceSummary incident={incident} />
      </ReadOnlySection>

      <ReadOnlySection
        meta={
          <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
            {actions.length} recorded
          </span>
        }
        title="Remediation actions"
      >
        {actions.length === 0 ? (
          <EmptyReadOnlyState>No remediation action has been recorded for this incident.</EmptyReadOnlyState>
        ) : (
          actions.map((action) => {
            const actionState = actionStatus(action);
            const target = primitiveEntries(action.target);

            return (
              <div className="border-b border-white/7 px-5 py-5 last:border-b-0 sm:px-6" key={action.id}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-white/78">{humanize(action.action_type)}</p>
                    <p className="mt-1 font-mono text-[10px] text-white/28">
                      {shortId(action.id)} · {action.adapter} · proposed {formatUtc(action.proposed_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {action.pull_request?.pull_request_url ? (
                      <a
                        className="inline-flex items-center gap-1.5 text-xs text-white/46 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                        href={action.pull_request.pull_request_url}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        Review PR
                        <ArrowUpRightIcon className="size-3.5" />
                      </a>
                    ) : null}
                    <Status label={actionState.label} tone={actionState.tone} />
                  </div>
                </div>
                {target.length > 0 ? (
                  <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
                    {target.map(([key, value]) => (
                      <span className="font-mono text-[10px] text-white/34" key={key}>
                        {humanize(key)}: <span className="text-white/58">{String(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </ReadOnlySection>

      <ReadOnlySection
        meta={
          <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
            UTC
          </span>
        }
        title="Timeline"
      >
        {timeline.length === 0 ? (
          <EmptyReadOnlyState>No timeline events have been recorded.</EmptyReadOnlyState>
        ) : (
          timeline.map((event) => (
            <div
              className="grid gap-2 border-b border-white/7 px-5 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-6"
              key={event.id}
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="size-1.5 shrink-0 bg-white/28" />
                <p className="truncate text-sm text-white/62">
                  {humanize(event.event_type)}
                  {event.event_type === "signal_repeated" && repeatedSignals.length > 1
                    ? ` · ${repeatedSignals.length} events`
                    : ""}
                </p>
              </div>
              <time className="font-mono text-[10px] text-white/28" dateTime={event.created_at}>
                {formatUtc(event.created_at)}
              </time>
            </div>
          ))
        )}
      </ReadOnlySection>
    </ReadOnlyPage>
  );
}
