import type { ActivityItem } from "@/lib/histograph-api";

function formatEvent(event: ActivityItem) {
  const names: Record<string, string> = {
    deployment_observed: "Deployment observed",
    change_observed: "Change observed",
    created: "Incident opened",
    investigation_updated: "Investigation updated",
    proposed: "Remediation proposed",
    approved: "Remediation approved",
    execution_succeeded: "Execution succeeded",
    recovery_verified: "Recovery verified",
  };

  return names[event.event_type] ?? event.event_type.replaceAll("_", " ");
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

export function Activity({ items }: { items: ActivityItem[] }) {
  return (
    <section className="bg-[#0a0a0a]" id="activity">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">Recent activity</h2>
        <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">UTC</span>
      </div>
      <div className="border-t border-white/8">
        {items.length > 0 ? (
          items.slice(0, 6).map((item) => (
            <div
              className="grid min-h-13 grid-cols-[1fr_auto] items-center gap-5 border-b border-white/6 px-5 last:border-b-0 sm:px-6"
              key={item.id}
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="size-1.5 shrink-0 bg-white/28" />
                <p className="truncate text-sm capitalize text-white/58">{formatEvent(item)}</p>
              </div>
              <time className="font-mono text-[10px] text-white/26" dateTime={item.created_at}>
                {formatTime(item.created_at)}
              </time>
            </div>
          ))
        ) : (
          <div className="flex min-h-24 items-center px-5 sm:px-6">
            <p className="text-sm text-white/34">No activity yet</p>
          </div>
        )}
      </div>
    </section>
  );
}
