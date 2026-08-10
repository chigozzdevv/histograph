const sharedOutcomeCells = Array.from({ length: 24 }, (_, index) => index);

const comparisonScale = {
  boundary: "62%",
  released: "0%",
  stable: "95.33%",
} as const;

function Metric({
  detail,
  label,
  tone = "neutral",
  value,
}: {
  detail: string;
  label: string;
  tone?: "critical" | "neutral" | "violet";
  value: string;
}) {
  const valueClass = {
    critical: "text-critical",
    neutral: "text-white/78",
    violet: "text-brand-soft",
  }[tone];

  return (
    <div className="min-w-0 px-4 py-4 sm:px-6 sm:py-5">
      <dt className="font-mono text-[9px] leading-4 tracking-[0.1em] text-white/34 uppercase">
        {label}
      </dt>
      <dd className={`mt-2 text-xl tracking-[-0.04em] sm:text-2xl ${valueClass}`}>
        {value}
      </dd>
      <dd className="mt-1 font-mono text-[9px] leading-4 text-white/28">{detail}</dd>
    </div>
  );
}

function ComparisonRow({
  label,
  tone,
  value,
  width,
}: {
  label: string;
  tone: "released" | "stable";
  value: string;
  width: string;
}) {
  const fillClass = tone === "stable" ? "bg-white/58" : "bg-brand-soft";
  const valueClass = tone === "stable" ? "text-white/74" : "text-brand-soft";

  return (
    <div>
      <div className="flex items-baseline justify-between gap-5">
        <p className="font-mono text-[10px] tracking-[0.08em] text-white/48 uppercase">
          {label}
        </p>
        <p className={`text-base tracking-[-0.03em] ${valueClass}`}>{value}</p>
      </div>

      <div className="relative mt-3 h-3 border border-white/10 bg-white/[0.025]">
        <span
          aria-hidden="true"
          className={`absolute inset-y-0 left-0 ${tone === "released" ? "w-px" : ""} ${fillClass}`}
          style={tone === "stable" ? { width } : undefined}
        />
        <span
          aria-hidden="true"
          className="absolute -top-1.5 -bottom-1.5 border-l border-dashed border-critical/72"
          style={{ left: comparisonScale.boundary }}
        />
      </div>
    </div>
  );
}

export function ReleaseEvidence() {
  return (
    <figure className="overflow-hidden border border-white/10 bg-[#090909]">
      <div className="flex min-h-14 items-center justify-between gap-4 border-b border-white/8 px-4 sm:px-6">
        <div className="min-w-0">
          <p className="truncate text-sm text-white/76">Production recall</p>
          <p className="mt-0.5 font-mono text-[9px] tracking-[0.08em] text-white/34 uppercase">
            Same-window comparison
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-critical/82 uppercase">
          <span aria-hidden="true" className="size-1.5 bg-critical" />
          Boundary crossed
        </div>
      </div>

      <dl className="grid grid-cols-2 border-b border-white/8 sm:grid-cols-3">
        <Metric detail="stable · v1" label="Reference" value="14.3%" />
        <div className="border-l border-white/8">
          <Metric detail="feature release · v2" label="Released" tone="violet" value="0.0%" />
        </div>
        <div className="col-span-2 border-t border-white/8 sm:col-span-1 sm:border-t-0 sm:border-l">
          <Metric detail="healthy at 9.3%" label="Allowed decrease" tone="critical" value="5.0 pp" />
        </div>
      </dl>

      <div className="relative px-4 py-6 sm:px-6 sm:py-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:100%_50%,12.5%_100%]"
        />

        <div
          aria-label="On the same labeled production window, stable version 1 has 14.3 percent recall and released version 2 has 0 percent recall. The healthy boundary is 9.3 percent."
          className="relative border border-white/8 bg-[#090909]/94 px-4 py-5 sm:px-6 sm:py-6"
          role="img"
        >
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-white/8 pb-4">
            <p className="text-sm text-white/68">Recall on the shared sample</p>
            <div className="flex items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-critical/76 uppercase">
              <span aria-hidden="true" className="h-3 border-l border-dashed border-critical/72" />
              Healthy boundary · 9.3%
            </div>
          </div>

          <div className="mt-6 space-y-7">
            <ComparisonRow
              label="Stable · v1"
              tone="stable"
              value="14.3%"
              width={comparisonScale.stable}
            />
            <ComparisonRow
              label="Feature release · v2"
              tone="released"
              value="0.0%"
              width={comparisonScale.released}
            />
          </div>

          <div className="mt-4 flex items-center justify-between font-mono text-[9px] text-white/26">
            <span>0%</span>
            <span>Recall scale · 15%</span>
          </div>
        </div>
      </div>

      <div className="border-t border-white/8 px-4 py-4 sm:px-6 sm:py-5">
        <div className="flex items-end justify-between gap-5">
          <div>
            <p className="font-mono text-[9px] tracking-[0.1em] text-white/34 uppercase">
              Shared labeled outcomes
            </p>
            <p className="mt-1 text-xs leading-5 text-white/38">
              Both releases evaluated on the same production window
            </p>
          </div>
          <p className="shrink-0 font-mono text-[10px] text-white/54">240 shared</p>
        </div>
        <div
          aria-hidden="true"
          className="mt-4 grid grid-cols-[repeat(24,minmax(0,1fr))] gap-1"
        >
          {sharedOutcomeCells.map((cell) => (
            <span className="h-2 bg-white/26" key={cell} />
          ))}
        </div>
      </div>

      <figcaption className="sr-only">
        Stable version 1 and feature release version 2 are compared on the same 240 labeled
        production outcomes. Recall is 14.3 percent for stable version 1 and 0 percent for released
        version 2, crossing the 9.3 percent healthy boundary implied by the allowed 5 percentage
        point decrease.
      </figcaption>
    </figure>
  );
}
