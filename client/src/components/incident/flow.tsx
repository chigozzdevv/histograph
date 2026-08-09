type NodeKind = "dataset" | "features" | "model" | "deployment";

type GraphNodeProps = {
  className: string;
  kind: NodeKind;
  label: string;
  tone?: "default" | "lineage" | "brand";
};

const toneStyles = {
  default: "border-white/12 bg-midnight/92 text-ink-soft",
  lineage: "border-lineage/30 bg-lineage/7 text-lineage",
  brand: "border-brand/30 bg-brand/7 text-brand-soft",
} as const;

function NodeIcon({ kind }: { kind: NodeKind }) {
  if (kind === "dataset") {
    return (
      <svg aria-hidden="true" className="size-3.5" fill="none" viewBox="0 0 16 16">
        <ellipse cx="8" cy="4" rx="4.5" ry="2" stroke="currentColor" />
        <path d="M3.5 4v4c0 1.1 2 2 4.5 2s4.5-.9 4.5-2V4m-9 4v4c0 1.1 2 2 4.5 2s4.5-.9 4.5-2V8" stroke="currentColor" />
      </svg>
    );
  }

  if (kind === "features") {
    return (
      <svg aria-hidden="true" className="size-3.5" fill="none" viewBox="0 0 16 16">
        <circle cx="4" cy="4" r="1.5" stroke="currentColor" />
        <circle cx="12" cy="4" r="1.5" stroke="currentColor" />
        <circle cx="8" cy="12" r="1.5" stroke="currentColor" />
        <path d="m5.2 5 2 5.4M10.8 5l-2 5.4M5.5 4h5" stroke="currentColor" />
      </svg>
    );
  }

  if (kind === "model") {
    return (
      <svg aria-hidden="true" className="size-3.5" fill="none" viewBox="0 0 16 16">
        <path d="m8 2 5 3v6l-5 3-5-3V5l5-3Z" stroke="currentColor" />
        <path d="m3.5 5.3 4.5 2.6 4.5-2.6M8 8v5.5" stroke="currentColor" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" className="size-3.5" fill="none" viewBox="0 0 16 16">
      <path d="M4 4h8v8H4z" stroke="currentColor" />
      <path d="M6.5 8h5m0 0-2-2m2 2-2 2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GraphNode({ className, kind, label, tone = "default" }: GraphNodeProps) {
  return (
    <div
      className={`graph-node absolute z-10 flex items-center gap-2 border px-2.5 py-2 font-mono text-[9px] whitespace-nowrap shadow-[0_12px_30px_rgba(0,0,0,0.24)] sm:px-3 sm:text-[10px] ${toneStyles[tone]} ${className}`}
    >
      <NodeIcon kind={kind} />
      <span>{label}</span>
    </div>
  );
}

function Connections() {
  const route =
    "M118 132C182 132 220 230 298 230C372 230 402 130 486 130C520 184 510 270 454 314H560";

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 size-full"
      preserveAspectRatio="none"
      viewBox="0 0 620 420"
    >
      <defs>
        <linearGradient id="lineage-gradient" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#ff5f6d" />
          <stop offset="0.38" stopColor="#36cfc9" />
          <stop offset="0.72" stopColor="#7182ff" />
          <stop offset="1" stopColor="#42c99a" />
        </linearGradient>
        <filter id="lineage-signal-glow" x="-300%" y="-300%" width="700%" height="700%">
          <feGaussianBlur result="blur" stdDeviation="3" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <path
        d="M78 62C84 88 102 103 118 132"
        fill="none"
        stroke="#ff5f6d"
        strokeDasharray="3 7"
        strokeLinecap="round"
        strokeOpacity="0.5"
      />
      <path
        d={route}
        fill="none"
        stroke="#223249"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
      <path
        className="lineage-route"
        d={route}
        fill="none"
        stroke="url(#lineage-gradient)"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
      <circle
        className="lineage-signal"
        fill="#f6f8fb"
        filter="url(#lineage-signal-glow)"
        r="3"
      >
        <animateMotion dur="7s" path={route} repeatCount="indefinite" />
      </circle>
    </svg>
  );
}

export function IncidentFlow() {
  return (
    <figure className="relative mx-auto w-full max-w-170 lg:ml-auto">
      <div className="absolute -inset-10 -z-10 bg-[radial-gradient(circle_at_center,rgba(113,130,255,0.12),transparent_68%)] blur-2xl" />

      <div className="lineage-canvas relative min-h-95 overflow-hidden border border-white/10 bg-[#081421]/78 shadow-[0_30px_100px_rgba(0,0,0,0.28)] sm:aspect-[1.47] sm:min-h-0">
        <Connections />

        <div className="schema-chip absolute top-[8%] left-[7%] z-10 inline-flex items-center gap-2 border border-critical/20 bg-[#e8eaee] px-3 py-2 font-mono text-[9px] text-[#1a1f2a] shadow-[0_12px_28px_rgba(0,0,0,0.2)] sm:text-[10px]">
          <span className="schema-pulse size-1.5 rounded-full bg-critical" />
          schema change
        </div>

        <GraphNode
          className="top-[27%] left-[7%]"
          kind="dataset"
          label="transactions_v4"
          tone="lineage"
        />
        <GraphNode
          className="top-[51%] left-[37%]"
          kind="features"
          label="fraud_features"
        />
        <GraphNode
          className="top-[26%] left-[69%]"
          kind="model"
          label="fraud_model"
          tone="brand"
        />
        <GraphNode
          className="top-[70%] left-[57%] sm:left-[67%]"
          kind="deployment"
          label="v42 active"
          tone="brand"
        />

        <div className="verified-node absolute top-[69%] right-[3%] z-10 grid size-10 place-items-center rounded-full border border-success/30 bg-success/8 text-success shadow-[0_0_30px_rgba(66,201,154,0.12)] sm:size-11">
          <svg aria-hidden="true" className="size-5" fill="none" viewBox="0 0 20 20">
            <path
              d="m5.5 10 3 3 6-6"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.75"
            />
          </svg>
          <span className="absolute top-full mt-2 font-mono text-[8px] tracking-[0.08em] text-success uppercase">
            verified
          </span>
        </div>
      </div>

      <figcaption className="sr-only">
        A schema change travels through a DataHub lineage graph from a production dataset to
        a feature set and model. Histograph coordinates a rollback and verifies recovery.
      </figcaption>
    </figure>
  );
}
