import type { ReactNode } from "react";

export function ReadOnlyPage({
  title,
  description,
  children,
  action,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-400 px-5 py-7 sm:px-7 sm:py-9 lg:px-9 lg:py-10">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[1.65rem] leading-none font-normal tracking-[-0.035em] text-white">
            {title}
          </h1>
          {description ? (
            <p className="mt-3 max-w-2xl text-sm leading-6 text-white/42">{description}</p>
          ) : null}
        </div>
        {action}
      </div>

      <div className="mt-7 space-y-5">{children}</div>
    </div>
  );
}

export function ReadOnlySection({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden border border-white/10 bg-[#0a0a0a]">
      <div className="flex min-h-14 items-center justify-between gap-4 px-5 py-3 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">{title}</h2>
        {meta}
      </div>
      <div className="border-t border-white/8">{children}</div>
    </section>
  );
}

export function EmptyReadOnlyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-36 items-center px-5 py-8 sm:px-6">
      <p className="max-w-xl text-sm leading-6 text-white/38">{children}</p>
    </div>
  );
}

export function formatUtc(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}

export function humanize(value: string) {
  const words = value.replaceAll("_", " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Unknown";
}

export function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}
