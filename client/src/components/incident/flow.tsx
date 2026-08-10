type HealthTone = "alert" | "neutral" | "recovery";

type LineageNodeProps = {
  kind: "features" | "model" | "source" | "verified";
  label: string;
  x: number;
};

const healthBars: Array<{ height: number; tone: HealthTone }> = [
  { height: 52, tone: "neutral" },
  { height: 55, tone: "neutral" },
  { height: 54, tone: "neutral" },
  { height: 57, tone: "neutral" },
  { height: 55, tone: "neutral" },
  { height: 53, tone: "neutral" },
  { height: 56, tone: "neutral" },
  { height: 54, tone: "neutral" },
  { height: 55, tone: "neutral" },
  { height: 51, tone: "neutral" },
  { height: 45, tone: "alert" },
  { height: 34, tone: "alert" },
  { height: 20, tone: "alert" },
  { height: 15, tone: "alert" },
  { height: 23, tone: "alert" },
  { height: 33, tone: "recovery" },
  { height: 42, tone: "recovery" },
  { height: 49, tone: "recovery" },
  { height: 53, tone: "recovery" },
  { height: 55, tone: "recovery" },
  { height: 56, tone: "recovery" },
  { height: 57, tone: "recovery" },
];

const nodeStyles = {
  features: {
    className: "histograph-node--neutral",
    stroke: "rgba(255,255,255,0.48)",
  },
  model: {
    className: "histograph-node--model",
    stroke: "#b45cff",
  },
  source: {
    className: "histograph-node--source",
    stroke: "#b45cff",
  },
  verified: {
    className: "histograph-node--verified",
    stroke: "#77d9a7",
  },
} as const;

function NodeGlyph({ kind }: Pick<LineageNodeProps, "kind">) {
  if (kind === "source") {
    return (
      <g fill="none" stroke="#d4b1ff" strokeLinecap="square" strokeWidth="1.5">
        <path d="M-11-8H9M-11-2H11M-11 4H5" />
        <path d="M7 2v8M3 6h8" />
      </g>
    );
  }

  if (kind === "features") {
    return (
      <g fill="#dedede">
        <rect height="4" width="4" x="-9" y="-9" />
        <rect height="4" width="4" x="5" y="-9" />
        <rect height="4" width="4" x="-9" y="5" />
        <rect height="4" width="4" x="5" y="5" />
      </g>
    );
  }

  if (kind === "model") {
    return (
      <path
        d="M-13 1h5l5-9 7 17 5-9h5"
        fill="none"
        stroke="#f0e8ff"
        strokeLinecap="square"
        strokeLinejoin="miter"
        strokeWidth="1.5"
      />
    );
  }

  return (
    <path
      d="m-10 0 7 7 14-16"
      fill="none"
      stroke="#a9f3c9"
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeWidth="1.8"
    />
  );
}

function LineageNode({ kind, label, x }: LineageNodeProps) {
  const style = nodeStyles[kind];

  return (
    <g transform={`translate(${x} 410)`}>
      <g className={style.className}>
        <rect
          fill="#080808"
          height="48"
          stroke={style.stroke}
          strokeWidth="1.3"
          width="48"
          x="-24"
          y="-24"
        />
        <NodeGlyph kind={kind} />
      </g>
      <text
        className={kind === "verified" ? "fill-[#77d9a7]" : "fill-[#a7a7a7]"}
        fontFamily="var(--font-geist-mono)"
        fontSize="9"
        letterSpacing="0.08em"
        textAnchor="middle"
        y="62"
      >
        {label}
      </text>
    </g>
  );
}

function HealthHistogram() {
  return (
    <g>
      <g stroke="rgba(255,255,255,0.05)">
        <path d="M70 166H490" />
      </g>
      <path d="M70 250H490" stroke="rgba(255,255,255,0.14)" />
      {healthBars.map((bar, index) => {
        const x = 70 + index * 19;

        return (
          <rect
            className={`health-bar health-bar--${bar.tone}`}
            height={bar.height}
            key={`${x}-${bar.height}`}
            width="11"
            x={x}
            y={250 - bar.height}
          />
        );
      })}
    </g>
  );
}

function RegisterPattern() {
  const columns = [100, 220, 340, 460] as const;
  const rows = [110, 210, 310, 410, 510] as const;

  return (
    <g className="histograph-register" fill="none">
      <g>
        {rows.map((row) => (
          <path d={`M40 ${row}H520`} key={`row-${row}`} />
        ))}
        {columns.map((column) => (
          <path d={`M${column} 70V550`} key={`column-${column}`} />
        ))}
      </g>
    </g>
  );
}

function HistographSignal() {
  const tracePath = "M340 250V410H124";
  const recoveryPath = "M364 410H460V250";

  return (
    <svg
      aria-hidden="true"
      className="absolute inset-0 size-full scale-[1.06] sm:scale-100"
      preserveAspectRatio="xMidYMid meet"
      viewBox="0 0 560 620"
    >
      <defs>
        <filter id="histograph-violet-glow" x="-300%" y="-300%" width="700%" height="700%">
          <feGaussianBlur result="blur" stdDeviation="4" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="histograph-green-glow" x="-300%" y="-300%" width="700%" height="700%">
          <feGaussianBlur result="blur" stdDeviation="5" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <RegisterPattern />

      <text className="fill-white/52 font-mono text-[10px] tracking-[0.1em]" x="70" y="132">
        MODEL HEALTH
      </text>
      <HealthHistogram />

      <text className="fill-white/52 font-mono text-[10px] tracking-[0.1em]" x="76" y="342">
        DATAHUB LINEAGE
      </text>

      <g>
        <path
          d="M400 326V486"
          fill="none"
          stroke="rgba(119,217,167,0.16)"
          strokeDasharray="2 7"
        />
        <text
          fill="rgba(119,217,167,0.68)"
          fontFamily="var(--font-geist-mono)"
          fontSize="9"
          letterSpacing="0.08em"
          x="412"
          y="342"
        >
          RUNTIME / RECOVERY
        </text>
      </g>

      <g fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.25">
        <path d="M124 410H196M244 410H316" />
      </g>

      <path
        d={tracePath}
        fill="none"
        stroke="rgba(180,92,255,0.26)"
        strokeWidth="1.4"
      />
      <path
        className="histograph-trace"
        d={tracePath}
        fill="none"
        filter="url(#histograph-violet-glow)"
        pathLength="1"
        stroke="#b45cff"
        strokeLinecap="square"
        strokeLinejoin="miter"
        strokeWidth="2"
      />

      <path
        d={recoveryPath}
        fill="none"
        stroke="rgba(119,217,167,0.24)"
        strokeWidth="1.4"
      />
      <path
        className="histograph-recovery"
        d={recoveryPath}
        fill="none"
        filter="url(#histograph-green-glow)"
        pathLength="1"
        stroke="#77d9a7"
        strokeLinecap="square"
        strokeLinejoin="miter"
        strokeWidth="2"
      />

      <LineageNode kind="source" label="SOURCE" x={100} />
      <LineageNode kind="features" label="FEATURES" x={220} />
      <LineageNode kind="model" label="MODEL" x={340} />
      <LineageNode kind="verified" label="VERIFIED" x={460} />

      <circle cx="340" cy="250" fill="#b45cff" fillOpacity="0.58" r="2.5" />
      <circle cx="460" cy="250" fill="#77d9a7" fillOpacity="0.58" r="2.5" />

      <circle className="histograph-trace-signal" fill="#d4b1ff" filter="url(#histograph-violet-glow)" r="3">
        <animateMotion
          calcMode="linear"
          dur="8s"
          keyPoints="0;0;1;1"
          keyTimes="0;0.2;0.48;1"
          path={tracePath}
          repeatCount="indefinite"
        />
      </circle>
      <circle className="histograph-recovery-signal" fill="#a9f3c9" filter="url(#histograph-green-glow)" r="3.5">
        <animateMotion
          calcMode="linear"
          dur="8s"
          keyPoints="0;0;1;1"
          keyTimes="0;0.54;0.78;1"
          path={recoveryPath}
          repeatCount="indefinite"
        />
      </circle>
    </svg>
  );
}

export function IncidentFlow() {
  return (
    <figure className="histograph-canvas relative h-full min-h-80 overflow-hidden sm:min-h-105 lg:min-h-[calc(100svh-4.25rem)]">
      <HistographSignal />
      <figcaption className="sr-only">
        Model health degrades after a source change. Histograph traces the cause backward through
        DataHub lineage, then verifies recovery separately through fresh runtime evidence.
      </figcaption>
    </figure>
  );
}
