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
import type { Incident } from "@/lib/histograph-api";
import { getIncidents } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Incidents — Histograph",
  description: "Persisted production ML incidents and their current state.",
};

function incidentStatus(incident: Incident) {
  if (incident.status === "resolved") return { label: "Resolved", tone: "success" as const };
  if (incident.status === "closed") return { label: "Closed", tone: "neutral" as const };
  if (incident.status === "investigating") {
    return { label: "Investigating", tone: "warning" as const };
  }
  return { label: "Open", tone: "critical" as const };
}

export default async function IncidentsPage() {
  const incidents = await getIncidents();

  return (
    <ReadOnlyPage title="Incidents">
      <ReadOnlySection
        meta={
          <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
            {incidents.length} recorded
          </span>
        }
        title="Incident history"
      >
        {incidents.length === 0 ? (
          <EmptyReadOnlyState>No incidents have been recorded.</EmptyReadOnlyState>
        ) : (
          <div>
            {incidents.map((incident) => {
              const status = incidentStatus(incident);

              return (
                <Link
                  className="group grid gap-4 border-b border-white/7 px-5 py-5 transition-colors last:border-b-0 hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:px-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(9rem,0.55fr)_minmax(10rem,0.65fr)_auto] lg:items-center"
                  href={`/demo/incidents/${incident.id}`}
                  key={incident.id}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-white/82">
                      {humanize(incident.metric ?? incident.signal ?? "model")} degradation
                    </p>
                    <p className="mt-2 truncate font-mono text-[10px] text-white/28">
                      {incident.model} · {incident.version} · {shortId(incident.id)}
                    </p>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
                      Severity
                    </p>
                    <p className="mt-1.5 text-xs text-white/54">{humanize(incident.severity)}</p>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
                      Created
                    </p>
                    <time className="mt-1.5 block font-mono text-[10px] text-white/42" dateTime={incident.created_at}>
                      {formatUtc(incident.created_at)}
                    </time>
                  </div>
                  <div className="flex items-center justify-between gap-6 lg:justify-end">
                    <Status label={status.label} tone={status.tone} />
                    <ArrowUpRightIcon className="size-4 text-white/30 transition-colors group-hover:text-white/72" />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </ReadOnlySection>
    </ReadOnlyPage>
  );
}
