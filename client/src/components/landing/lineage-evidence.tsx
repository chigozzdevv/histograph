type NodeTone = "muted" | "success" | "violet";

type LineageNodeProps = {
  eyebrow: string;
  lines: readonly string[];
  marker?: boolean;
  tone?: NodeTone;
  width: number;
  x: number;
  y: number;
};

function LineageNode({
  eyebrow,
  lines,
  marker = false,
  tone = "muted",
  width,
  x,
  y,
}: LineageNodeProps) {
  const colors = {
    muted: {
      label: "rgba(255,255,255,0.48)",
      stroke: "rgba(255,255,255,0.2)",
      text: "rgba(255,255,255,0.58)",
    },
    success: {
      label: "rgba(255,255,255,0.42)",
      stroke: "rgba(119,217,167,0.78)",
      text: "#a9f3c9",
    },
    violet: {
      label: "rgba(255,255,255,0.42)",
      stroke: "#b45cff",
      text: "#d4b1ff",
    },
  }[tone];

  const firstLineY = lines.length > 1 ? 45 : 52;

  return (
    <g transform={`translate(${x} ${y})`}>
      <rect
        fill="#090909"
        height="78"
        stroke={colors.stroke}
        strokeWidth={tone === "muted" ? 1.25 : 1.5}
        width={width}
      />
      <text
        fill={colors.label}
        fontFamily="var(--font-geist-mono)"
        fontSize="8"
        letterSpacing="0.08em"
        x="12"
        y="21"
      >
        {eyebrow}
      </text>
      <text fill={colors.text} fontFamily="var(--font-geist-mono)" fontSize="9.5" x="12">
        {lines.map((line, index) => (
          <tspan dy={index === 0 ? 0 : 14} key={line} x="12" y={index === 0 ? firstLineY : undefined}>
            {line}
          </tspan>
        ))}
      </text>
      {marker ? <rect fill="#b45cff" height="4" width="4" x={width - 12} y="10" /> : null}
    </g>
  );
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-h-17 grid-cols-[6.25rem_minmax(0,1fr)] items-center gap-4 border-t border-white/8 px-4 py-3 sm:px-5">
      <dt className="font-mono text-[9px] tracking-[0.1em] text-white/34 uppercase">{label}</dt>
      <dd className="min-w-0 font-mono text-[10px] leading-4 text-white/64">{value}</dd>
    </div>
  );
}

function MobileLineageNode({
  eyebrow,
  label,
  meta,
  tone = "violet",
}: {
  eyebrow: string;
  label: string;
  meta: string;
  tone?: "success" | "violet";
}) {
  const toneClasses =
    tone === "success"
      ? "border-success/60 text-success"
      : "border-brand-soft/60 text-brand-soft";

  return (
    <div className="relative pl-7">
      <span
        aria-hidden="true"
        className={`absolute top-1/2 left-2 size-2 -translate-x-1/2 -translate-y-1/2 border bg-[#090909] ${toneClasses}`}
      />
      <div className={`border bg-[#090909] px-4 py-3 ${toneClasses}`}>
        <p className="font-mono text-[8px] tracking-[0.1em] text-white/34 uppercase">
          {eyebrow}
        </p>
        <div className="mt-2 flex min-w-0 items-center justify-between gap-3">
          <p className="min-w-0 font-mono text-[10px] leading-4 text-current">{label}</p>
          <p className="shrink-0 font-mono text-[8px] tracking-[0.06em] text-white/30 uppercase">
            {meta}
          </p>
        </div>
      </div>
    </div>
  );
}

export function LineageEvidence() {
  return (
    <figure className="overflow-hidden border border-white/10 bg-[#090909]">
      <div className="flex min-h-14 items-center justify-between gap-5 border-b border-white/8 px-4 sm:px-6">
        <div>
          <p className="text-sm text-white/76">DataHub investigation</p>
          <p className="mt-0.5 font-mono text-[9px] tracking-[0.08em] text-white/34 uppercase">
            Persisted lineage evidence
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-brand-soft uppercase">
          <span aria-hidden="true" className="size-1.5 bg-brand-soft" />
          Path isolated
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 px-3 py-6 sm:px-6 sm:py-8">
          <div className="relative py-1 sm:hidden">
            <span
              aria-hidden="true"
              className="absolute top-7 bottom-7 left-2 w-px bg-gradient-to-b from-brand-soft/70 via-brand-soft/35 to-success/60"
            />
            <div className="space-y-3">
              <MobileLineageNode
                eyebrow="Dataset"
                label="momtsim.transactions"
                meta="source"
              />
              <MobileLineageNode eyebrow="Changed feature" label="amount" meta="v2" />
              <MobileLineageNode
                eyebrow="Affected model"
                label="mobile-money-fraud-detection"
                meta="model"
              />
              <MobileLineageNode
                eyebrow="Deployment"
                label="production"
                meta="reached"
                tone="success"
              />
            </div>
            <p className="mt-4 border-l border-white/12 pl-3 font-mono text-[9px] leading-4 text-white/30">
              Unaffected branch · account_velocity_24h
            </p>
          </div>

          <svg aria-hidden="true" className="hidden h-auto w-full sm:block" viewBox="0 0 760 390">
            <defs>
              <filter id="lineage-evidence-glow" height="300%" width="300%" x="-100%" y="-100%">
                <feGaussianBlur result="blur" stdDeviation="3" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <g fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="1">
              <path d="M0 48H760M0 146H760M0 244H760M0 342H760" />
              <path d="M52 0V390M180 0V390M308 0V390M436 0V390M564 0V390M692 0V390" />
            </g>

            <g fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth="1.25">
              <path d="M180 194H225V289H270" />
              <path d="M420 289H450V194H500" />
            </g>

            <g
              fill="none"
              filter="url(#lineage-evidence-glow)"
              stroke="#b45cff"
              strokeWidth="2"
            >
              <path d="M180 194H225V104H270" />
              <path d="M395 104H450V194H500" />
            </g>
            <path
              d="M635 194H650"
              fill="none"
              stroke="rgba(119,217,167,0.76)"
              strokeWidth="1.5"
            />

            <LineageNode
              eyebrow="DATASET"
              lines={["momtsim.", "transactions"]}
              marker
              tone="violet"
              width={130}
              x={50}
              y={155}
            />
            <LineageNode
              eyebrow="FEATURE"
              lines={["amount"]}
              marker
              tone="violet"
              width={125}
              x={270}
              y={65}
            />
            <LineageNode
              eyebrow="FEATURE"
              lines={["account_velocity", "_24h"]}
              width={150}
              x={270}
              y={250}
            />
            <LineageNode
              eyebrow="MODEL"
              lines={["mobile-money", "fraud-detection"]}
              tone="violet"
              width={135}
              x={500}
              y={155}
            />
            <LineageNode
              eyebrow="DEPLOYMENT"
              lines={["production"]}
              tone="success"
              width={100}
              x={650}
              y={155}
            />
          </svg>
        </div>

        <dl className="border-t border-white/8 bg-white/[0.012] lg:border-t-0 lg:border-l">
          <div className="flex min-h-14 items-center px-4 sm:px-5">
            <p className="font-mono text-[9px] tracking-[0.12em] text-white/34 uppercase">
              Root-cause evidence
            </p>
          </div>
          <EvidenceRow label="Changed feature" value="amount · v2" />
          <EvidenceRow label="Reached" value="mobile-money-fraud-detection" />
          <EvidenceRow label="Change time" value="14:06 UTC" />
          <EvidenceRow label="Monitor window" value="14:12–14:18 UTC" />
          <div className="flex min-h-16 items-center gap-2 border-t border-white/8 px-4 sm:px-5">
            <span aria-hidden="true" className="size-1.5 bg-success" />
            <span className="font-mono text-[9px] tracking-[0.1em] text-success uppercase">
              Corroborated
            </span>
          </div>
        </dl>
      </div>

      <figcaption className="sr-only">
        DataHub highlights the implicated path from the MoMTSim transaction dataset through the
        changed amount feature and mobile-money fraud model to production. The unaffected account
        velocity feature remains muted, and the incident retains the corroborating change and
        monitor window.
      </figcaption>
    </figure>
  );
}
