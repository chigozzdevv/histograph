"use client";

import {
  type KeyboardEvent,
  type ReactNode,
  useId,
  useRef,
  useState,
} from "react";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "investigation", label: "Investigation" },
  { id: "remediation", label: "Remediation" },
  { id: "recovery", label: "Recovery" },
] as const;

type TabId = (typeof tabs)[number]["id"];

const tabState: Record<
  TabId,
  { label: string; tone: "critical" | "success" | "violet" }
> = {
  overview: { label: "Incident open", tone: "critical" },
  investigation: { label: "Probable cause", tone: "violet" },
  remediation: { label: "Approved", tone: "violet" },
  recovery: { label: "Resolved", tone: "success" },
};

function Status({
  label,
  tone,
}: {
  label: string;
  tone: "critical" | "success" | "violet";
}) {
  const dot = {
    critical: "bg-critical",
    success: "bg-success",
    violet: "bg-brand-soft",
  }[tone];

  return (
    <span className="inline-flex items-center gap-2 text-xs text-white/54">
      <span aria-hidden="true" className={`size-1.5 ${dot}`} />
      {label}
    </span>
  );
}

function MonoLabel({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[9px] tracking-[0.13em] text-white/30 uppercase">
      {children}
    </p>
  );
}

function WorkspaceHeader({ activeTab }: { activeTab: TabId }) {
  const state = tabState[activeTab];

  return (
    <div className="flex min-h-14 items-center border-b border-white/10">
      <div className="flex h-14 w-14 shrink-0 items-center justify-center border-r border-white/10">
        <span aria-hidden="true" className="flex h-5 items-end gap-0.5">
          <span className="h-2.5 w-1 bg-white/48" />
          <span className="h-4 w-1 bg-white/68" />
          <span className="h-3 w-1 bg-white" />
        </span>
      </div>

      <div className="min-w-0 px-4 sm:px-5">
        <p className="truncate text-sm text-white/84">mobile-money-fraud</p>
        <p className="mt-0.5 truncate font-mono text-[9px] text-white/28">
          production · incident HG-184
        </p>
      </div>

      <div className="ml-auto hidden h-14 items-center border-l border-white/10 px-5 sm:flex">
        <Status label={state.label} tone={state.tone} />
      </div>
    </div>
  );
}

function IncidentHeader({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-16 items-center justify-between gap-4 border-b border-white/8 px-4 py-3 sm:px-6">
      <div className="min-w-0 flex-1">
        <MonoLabel>Incident HG-184</MonoLabel>
        <p className="mt-1 text-xs leading-5 text-white/76 sm:text-sm">{title}</p>
      </div>
      {children ? <div className="shrink-0">{children}</div> : null}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "critical" | "neutral" | "violet";
}) {
  const valueClass = {
    critical: "text-critical",
    neutral: "text-white/88",
    violet: "text-brand-soft",
  }[tone];

  return (
    <div className="min-w-0 px-4 py-5 sm:px-5">
      <MonoLabel>{label}</MonoLabel>
      <p className={`mt-3 text-2xl tracking-[-0.045em] ${valueClass}`}>{value}</p>
      <p className="mt-1 truncate font-mono text-[9px] text-white/25">{detail}</p>
    </div>
  );
}

function RecallChart() {
  return (
    <div className="relative min-h-60 overflow-hidden px-4 pt-7 pb-4 sm:px-6">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.045)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.045)_1px,transparent_1px)] bg-[size:100%_25%,12.5%_100%]" />
      <div className="relative flex items-center justify-between">
        <MonoLabel>Recall · labeled outcomes</MonoLabel>
        <span className="font-mono text-[9px] text-white/24">12:00—14:30 UTC</span>
      </div>
      <svg
        aria-labelledby="workspace-recall-title workspace-recall-description"
        className="relative mt-5 h-40 w-full overflow-visible"
        preserveAspectRatio="none"
        role="img"
        viewBox="0 0 680 160"
      >
        <title id="workspace-recall-title">Candidate model recall degradation</title>
        <desc id="workspace-recall-description">
          Recall remains near 14.3 percent, then falls to zero after the feature release.
        </desc>
        <defs>
          <linearGradient id="workspace-recall-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#b45cff" stopOpacity="0.2" />
            <stop offset="1" stopColor="#b45cff" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M0 35L66 38L132 34L198 37L264 35L330 42L384 40L430 78L472 121L520 139L580 142L680 142V160H0Z"
          fill="url(#workspace-recall-area)"
        />
        <path
          d="M0 35L66 38L132 34L198 37L264 35L330 42L384 40L430 78L472 121L520 139L580 142L680 142"
          fill="none"
          stroke="#b45cff"
          strokeLinecap="square"
          strokeLinejoin="miter"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
        <path
          d="M394 6V151"
          stroke="#ff7380"
          strokeDasharray="3 5"
          strokeOpacity="0.7"
          vectorEffect="non-scaling-stroke"
        />
        <circle cx="394" cy="45" fill="#ff7380" r="3" vectorEffect="non-scaling-stroke" />
        <text
          fill="rgba(255,115,128,0.72)"
          fontFamily="var(--font-geist-mono)"
          fontSize="9"
          x="404"
          y="16"
        >
          FEATURE V2 OBSERVED
        </text>
      </svg>
    </div>
  );
}

function OverviewPanel() {
  return (
    <div>
      <IncidentHeader title="Production recall crossed its allowed decrease">
        <Status label="Threshold crossed" tone="critical" />
      </IncidentHeader>

      <div className="grid grid-cols-2 divide-x divide-white/8 border-b border-white/8 lg:grid-cols-4">
        <Metric detail="stable · v1" label="Reference" value="14.3%" />
        <Metric detail="feature release · v2" label="Observed" tone="critical" value="0.0%" />
        <div className="border-t border-white/8 lg:border-t-0">
          <Metric detail="14.3 percentage points" label="Decrease" tone="critical" value="−14.3 pp" />
        </div>
        <div className="border-t border-white/8 lg:border-t-0">
          <Metric detail="10 min evaluation" label="Sample" value="240" />
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1.65fr)_minmax(14rem,0.65fr)]">
        <RecallChart />
        <div className="border-t border-white/8 bg-white/[0.012] px-4 py-6 lg:border-t-0 lg:border-l lg:px-5">
          <MonoLabel>Next evidence</MonoLabel>
          <p className="mt-4 text-base tracking-[-0.02em] text-white/76">Trace the changed input</p>
          <p className="mt-2 text-sm leading-6 text-white/38">
            DataHub links the affected model to the amount feature released before the breach.
          </p>
          <div className="mt-7 border-t border-white/8 pt-4">
            <div className="flex items-center justify-between font-mono text-[10px]">
              <span className="text-white/28">Lineage matches</span>
              <span className="text-brand-soft">1 upstream change</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LineageNode({
  label,
  meta,
  active = false,
}: {
  label: string;
  meta: string;
  active?: boolean;
}) {
  return (
    <div
      className={`relative z-10 flex min-h-20 min-w-0 flex-col justify-center border bg-[#090909] px-4 py-4 ${
        active ? "border-brand-soft/70" : "border-white/16"
      }`}
    >
      <p
        className={`min-w-0 font-mono text-[10px] leading-4 break-words ${
          active ? "text-brand-soft" : "text-white/68"
        }`}
      >
        {label}
      </p>
      <p className="mt-2 font-mono text-[9px] text-white/30">{meta}</p>
    </div>
  );
}

function LineageConnector() {
  return (
    <span
      aria-hidden="true"
      className="mx-auto h-8 w-px bg-brand-soft/45 sm:h-px sm:w-full"
    />
  );
}

function InvestigationPanel() {
  return (
    <div>
      <IncidentHeader title="DataHub narrowed the regression to one upstream release">
        <Status label="Probable cause" tone="violet" />
      </IncidentHeader>

      <div className="grid lg:grid-cols-[minmax(0,1.5fr)_minmax(17rem,0.65fr)]">
        <div className="relative min-w-0 overflow-hidden border-b border-white/8 lg:border-r lg:border-b-0">
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.038)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.038)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
          <div className="relative px-4 py-7 sm:px-6 sm:py-8">
            <div className="flex items-center justify-between">
              <MonoLabel>DataHub lineage</MonoLabel>
              <span className="font-mono text-[9px] text-white/24">1 hop upstream</span>
            </div>

            <div className="mt-10 grid min-w-0 sm:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)_2.5rem_minmax(0,1fr)] sm:items-center">
              <LineageNode label="momtsim.transactions" meta="dataset" />
              <LineageConnector />
              <LineageNode active label="amount" meta="feature · v2" />
              <LineageConnector />
              <LineageNode label="mobile-money-fraud-detection" meta="model · production" />
            </div>

            <div className="relative mt-1 border border-brand-soft/28 bg-brand/5 px-4 py-4 sm:flex sm:items-center sm:justify-between sm:gap-6">
              <div>
                <MonoLabel>Observed change</MonoLabel>
                <p className="mt-2 text-sm text-white/72">amount scale multiplier</p>
              </div>
              <p className="mt-3 font-mono text-sm text-brand-soft sm:mt-0">1 → 100</p>
            </div>
          </div>
        </div>

        <div className="bg-white/[0.012]">
          <div className="border-b border-white/8 px-4 py-5 sm:px-5">
            <MonoLabel>Corroborating evidence</MonoLabel>
          </div>
          <dl className="divide-y divide-white/8">
            <div className="px-4 py-5 sm:px-5">
              <dt className="font-mono text-[9px] text-white/28">ASSET</dt>
              <dd className="mt-2 text-sm text-white/66">mobile-money-amount-feature</dd>
            </div>
            <div className="grid grid-cols-2 divide-x divide-white/8">
              <div className="px-4 py-5 sm:px-5">
                <dt className="font-mono text-[9px] text-white/28">VERSION</dt>
                <dd className="mt-2 text-sm text-brand-soft">v2</dd>
              </div>
              <div className="px-4 py-5 sm:px-5">
                <dt className="font-mono text-[9px] text-white/28">LEAD TIME</dt>
                <dd className="mt-2 text-sm text-white/66">6 min</dd>
              </div>
            </div>
            <div className="px-4 py-5 sm:px-5">
              <dt className="font-mono text-[9px] text-white/28">MATCH</dt>
              <dd className="mt-2 text-sm leading-6 text-white/54">
                Feature release is upstream of the affected model and precedes degradation.
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}

function Step({
  label,
  detail,
  complete = false,
}: {
  label: string;
  detail: string;
  complete?: boolean;
}) {
  return (
    <li className="relative flex min-w-0 flex-1 items-start gap-3">
      <span
        aria-hidden="true"
        className={`relative z-10 mt-0.5 flex size-5 shrink-0 items-center justify-center border bg-[#090909] font-mono text-[9px] ${
          complete ? "border-brand-soft text-brand-soft" : "border-white/20 text-white/28"
        }`}
      >
        {complete ? "✓" : "·"}
      </span>
      <div className="min-w-0">
        <p className="text-xs text-white/62">{label}</p>
        <p className="mt-1 font-mono text-[9px] text-white/24">{detail}</p>
      </div>
    </li>
  );
}

function RemediationPanel() {
  return (
    <div>
      <IncidentHeader title="Rollback generated from the imported deployment manifest">
        <Status label="Approved" tone="violet" />
      </IncidentHeader>

      <div className="grid lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
        <div className="border-b border-white/8 px-4 py-7 sm:px-6 sm:py-8 lg:border-r lg:border-b-0">
          <div className="flex items-start justify-between gap-6">
            <div>
              <MonoLabel>Protective action</MonoLabel>
              <p className="mt-4 text-xl tracking-[-0.035em] text-white/82">
                Roll back the feature configuration
              </p>
            </div>
            <span className="border border-brand-soft/48 px-2.5 py-1 font-mono text-[9px] text-brand-soft">
              ROLLBACK
            </span>
          </div>

          <div className="mt-8 grid border border-white/10 sm:grid-cols-3 sm:divide-x sm:divide-white/8">
            <div className="px-4 py-5">
              <MonoLabel>Target</MonoLabel>
              <p className="mt-3 truncate font-mono text-[10px] text-white/62">amount feature</p>
            </div>
            <div className="border-t border-white/8 px-4 py-5 sm:border-t-0">
              <MonoLabel>Current</MonoLabel>
              <p className="mt-3 font-mono text-[10px] text-critical">v2 · ×100</p>
            </div>
            <div className="border-t border-white/8 px-4 py-5 sm:border-t-0">
              <MonoLabel>Rollback</MonoLabel>
              <p className="mt-3 font-mono text-[10px] text-success">v1 · ×1</p>
            </div>
          </div>

          <ol className="relative mt-10 grid gap-5 sm:grid-cols-3 sm:gap-7 before:absolute before:top-2.5 before:right-3 before:left-3 before:hidden before:h-px before:bg-white/10 sm:before:block">
            <Step complete detail="14:16 UTC" label="Proposed" />
            <Step complete detail="Signed merge" label="Approved" />
            <Step detail="Runtime evidence pending" label="Applying" />
          </ol>
        </div>

        <div className="bg-white/[0.012]">
          <div className="border-b border-white/8 px-4 py-5 sm:px-5">
            <div className="flex items-center justify-between">
              <MonoLabel>GitHub approval</MonoLabel>
              <span className="font-mono text-[9px] text-success">MERGED</span>
            </div>
          </div>
          <div className="px-4 py-6 sm:px-5">
            <p className="font-mono text-[10px] text-white/35">histograph/rollback-hg-184</p>
            <p className="mt-3 text-base text-white/72">Restore amount feature v1</p>
            <div className="mt-7 border-y border-white/8 py-4">
              <div className="flex items-center justify-between text-xs">
                <span className="text-white/32">Pull request</span>
                <span className="font-mono text-white/60">#42</span>
              </div>
              <div className="mt-4 flex items-center justify-between text-xs">
                <span className="text-white/32">Deployment status</span>
                <span className="font-mono text-brand-soft">in progress</span>
              </div>
            </div>
            <p className="mt-5 text-xs leading-5 text-white/32">
              Desired Git state is recorded separately from observed runtime state.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function VerificationRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-h-16 items-center justify-between gap-5 border-t border-white/8 px-4 sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center border border-success/50 text-[10px] text-success">
          ✓
        </span>
        <span className="truncate text-sm text-white/62">{label}</span>
      </div>
      <span className="shrink-0 font-mono text-[9px] text-success">{value}</span>
    </div>
  );
}

function RecoveryPanel() {
  return (
    <div>
      <IncidentHeader title="Fresh production evidence passed the recovery gate">
        <Status label="Resolved" tone="success" />
      </IncidentHeader>

      <div className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <div className="border-b border-white/8 px-4 py-7 sm:px-6 sm:py-8 lg:border-r lg:border-b-0">
          <div className="flex items-end justify-between gap-4">
            <div>
              <MonoLabel>Recall after rollback</MonoLabel>
              <p className="mt-4 text-3xl tracking-[-0.05em] text-success">14.3%</p>
            </div>
            <p className="pb-1 font-mono text-[9px] text-white/28">240 fresh labeled outcomes</p>
          </div>

          <div className="mt-9 space-y-6">
            <div className="grid grid-cols-[5rem_minmax(0,1fr)_3rem] items-center gap-3">
              <span className="font-mono text-[9px] text-white/30">REFERENCE</span>
              <span className="relative h-2 bg-white/5">
                <span className="absolute inset-y-0 left-0 w-[71.5%] bg-white/48" />
              </span>
              <span className="text-right font-mono text-[9px] text-white/48">14.3%</span>
            </div>
            <div className="grid grid-cols-[5rem_minmax(0,1fr)_3rem] items-center gap-3">
              <span className="font-mono text-[9px] text-white/30">RECOVERED</span>
              <span className="relative h-2 bg-white/5">
                <span className="absolute inset-y-0 left-0 w-[71.5%] bg-success" />
              </span>
              <span className="text-right font-mono text-[9px] text-success">14.3%</span>
            </div>
          </div>

          <div className="mt-10 flex items-center justify-between border border-success/24 bg-success/[0.025] px-4 py-4">
            <div>
              <MonoLabel>Incident state</MonoLabel>
              <p className="mt-2 text-sm text-white/68">Recovery verified</p>
            </div>
            <span className="font-mono text-[10px] text-success">RESOLVED</span>
          </div>
        </div>

        <div className="bg-white/[0.012]">
          <div className="px-4 py-5 sm:px-5">
            <MonoLabel>Required proof</MonoLabel>
          </div>
          <VerificationRow label="Action execution recorded" value="SUCCEEDED" />
          <VerificationRow label="Feature rollback observed" value="v1 · ×1" />
          <VerificationRow label="Fresh monitor window passed" value="14.3%" />
          <VerificationRow label="Root cause confirmed" value="DATAHUB" />
        </div>
      </div>
    </div>
  );
}

const panels: Record<TabId, () => ReactNode> = {
  overview: OverviewPanel,
  investigation: InvestigationPanel,
  remediation: RemediationPanel,
  recovery: RecoveryPanel,
};

export function Workspace() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const instanceId = useId();
  const Panel = panels[activeTab];

  function focusTab(index: number) {
    const normalized = (index + tabs.length) % tabs.length;
    setActiveTab(tabs[normalized].id);
    tabRefs.current[normalized]?.focus();
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTab(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTab(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTab(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTab(tabs.length - 1);
    }
  }

  return (
    <div className="overflow-hidden border border-white/12 bg-[#090909] shadow-[0_24px_80px_rgba(0,0,0,0.32)]">
      <WorkspaceHeader activeTab={activeTab} />

      <div
        aria-label="Incident workspace views"
        className="grid grid-cols-4 border-b border-white/10"
        role="tablist"
      >
        {tabs.map((tab, index) => {
          const active = activeTab === tab.id;

          return (
            <button
              aria-controls={`${instanceId}-${tab.id}-panel`}
              aria-selected={active}
              className={`relative min-h-12 min-w-0 border-r border-white/8 px-1 text-[10px] transition-colors duration-200 focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:px-6 sm:text-xs ${
                active ? "bg-white/[0.045] text-white" : "text-white/38 hover:bg-white/[0.025] hover:text-white/66"
              }`}
              id={`${instanceId}-${tab.id}-tab`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              ref={(node) => {
                tabRefs.current[index] = node;
              }}
              role="tab"
              tabIndex={active ? 0 : -1}
              type="button"
            >
              {tab.label}
              {active ? (
                <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-px bg-brand-soft" />
              ) : null}
            </button>
          );
        })}
      </div>

      <div
        aria-labelledby={`${instanceId}-${activeTab}-tab`}
        id={`${instanceId}-${activeTab}-panel`}
        role="tabpanel"
        tabIndex={0}
      >
        <Panel />
      </div>
    </div>
  );
}
