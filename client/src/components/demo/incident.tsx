import Link from "next/link";

import { ArrowUpRightIcon } from "@/components/demo/icons";
import { Status } from "@/components/demo/status";
import type { Incident } from "@/lib/histograph-api";

export function IncidentPanel({ incident }: { incident: Incident | null }) {
  const active = incident && ["open", "investigating"].includes(incident.status);
  const label = incident
    ? incident.status === "resolved"
      ? "Resolved"
      : incident.status === "closed"
        ? "Closed"
        : incident.status.charAt(0).toUpperCase() + incident.status.slice(1)
    : "Clear";
  const tone = active ? "critical" : incident?.status === "resolved" ? "success" : "neutral";

  return (
    <section className="border-t border-white/8 bg-[#0a0a0a]" id="incidents">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">Incident</h2>
        <Status label={label} tone={tone} />
      </div>
      <div className="flex min-h-42 flex-col border-t border-white/8 px-5 py-5 sm:px-6">
        {incident ? (
          <>
            <p className="text-lg tracking-[-0.025em] text-white/82 capitalize">
              {incident.metric ?? incident.signal ?? "Model"} degradation
            </p>
            <p className="mt-2 font-mono text-[11px] text-white/32">
              {incident.version} · {incident.model}
            </p>
            <div className="mt-auto flex items-end justify-between pt-5">
              <div>
                <p className="font-mono text-[10px] tracking-[0.12em] text-white/30 uppercase">
                  {incident.metric ?? incident.signal ?? "Signal"}
                </p>
                <p className="mt-1 text-sm text-white/58">Root-cause analysis</p>
              </div>
              <Link
                aria-label="Open incident"
                className="text-white/42 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                href={`/demo/incidents/${incident.id}`}
              >
                <ArrowUpRightIcon className="size-4" />
              </Link>
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center">
            <p className="text-sm text-white/38">No active incident</p>
          </div>
        )}
      </div>
    </section>
  );
}
