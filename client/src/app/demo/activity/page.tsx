import type { Metadata } from "next";
import Link from "next/link";

import {
  EmptyReadOnlyState,
  formatUtc,
  humanize,
  ReadOnlyPage,
  ReadOnlySection,
  shortId,
} from "@/components/demo/read-only-page";
import type { ActivityItem, JsonValue } from "@/lib/histograph-api";
import { getActivity } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Activity — Histograph",
  description: "Chronological production ML incident-response activity.",
};

const eventNames: Record<string, string> = {
  deployment_observed: "Deployment observed",
  change_observed: "Change observed",
  created: "Incident opened",
  signal_repeated: "Monitor signal repeated",
  investigation_updated: "Investigation updated",
  proposed: "Remediation action proposed",
  approved: "Remediation action approved",
  rejected: "Remediation action rejected",
  execution_started: "Action execution started",
  execution_succeeded: "Action execution succeeded",
  execution_failed: "Action execution failed",
  recovery_verified: "Recovery verified",
  status_changed: "Incident status changed",
  scenario_resolved: "Controlled scenario completed",
  scenario_failed: "Controlled scenario failed",
};

function eventName(item: ActivityItem) {
  return eventNames[item.event_type] ?? humanize(item.event_type);
}

function primitiveDetails(details: Record<string, JsonValue>) {
  return Object.entries(details)
    .filter((entry): entry is [string, string | number | boolean] =>
      ["string", "number", "boolean"].includes(typeof entry[1]) &&
      !["occurred_at", "monitor_event_id", "asset_urn"].includes(entry[0]),
    )
    .slice(0, 3);
}

type DisplayActivity = ActivityItem & { occurrences: number };

function compactActivity(items: ActivityItem[]) {
  const rows: DisplayActivity[] = [];
  const repeatedByIncident = new Map<string, DisplayActivity>();

  items.forEach((item) => {
    if (item.event_type !== "signal_repeated") {
      rows.push({ ...item, occurrences: 1 });
      return;
    }

    const existing = repeatedByIncident.get(item.entity_id);
    if (existing) {
      existing.occurrences += 1;
      return;
    }

    const row = { ...item, occurrences: 1 };
    repeatedByIncident.set(item.entity_id, row);
    rows.push(row);
  });

  return rows.sort((left, right) => right.created_at.localeCompare(left.created_at));
}

export default async function ActivityPage() {
  const items = await getActivity();
  const rows = compactActivity(items);

  return (
    <ReadOnlyPage title="Activity">
      <ReadOnlySection
        meta={
          <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
            UTC · {items.length} events
          </span>
        }
        title="Event timeline"
      >
        {items.length === 0 ? (
          <EmptyReadOnlyState>No activity has been recorded.</EmptyReadOnlyState>
        ) : (
          rows.map((item) => {
            const details =
              item.event_type === "signal_repeated" ? [] : primitiveDetails(item.details);
            const body = (
              <>
                <span className="mt-1.5 size-1.5 shrink-0 bg-white/28" />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-white/68">
                    {eventName(item)}
                    {item.occurrences > 1 ? ` · ${item.occurrences} events` : ""}
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-white/26">
                    {humanize(item.category)} · {shortId(item.entity_id)}
                  </span>
                  {details.length > 0 ? (
                    <span className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                      {details.map(([key, value]) => (
                        <span className="font-mono text-[9px] text-white/28" key={key}>
                          {humanize(key)}: <span className="text-white/46">{String(value)}</span>
                        </span>
                      ))}
                    </span>
                  ) : null}
                </span>
                <time className="shrink-0 font-mono text-[10px] text-white/28" dateTime={item.created_at}>
                  {formatUtc(item.created_at)}
                </time>
              </>
            );

            const href =
              item.category === "incident"
                ? `/demo/incidents/${item.entity_id}`
                : item.category === "demo_run"
                  ? `/demo/playground?run=${item.entity_id}`
                  : null;

            return href ? (
              <Link
                className="flex gap-3 border-b border-white/7 px-5 py-4 transition-colors last:border-b-0 hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:px-6"
                href={href}
                key={item.id}
              >
                {body}
              </Link>
            ) : (
              <div className="flex gap-3 border-b border-white/7 px-5 py-4 last:border-b-0 sm:px-6" key={item.id}>
                {body}
              </div>
            );
          })
        )}
      </ReadOnlySection>
    </ReadOnlyPage>
  );
}
