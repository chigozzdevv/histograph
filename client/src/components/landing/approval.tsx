type ApprovalRowProps = {
  label: string;
  value: string;
  tone?: "default" | "success" | "brand";
};

function ApprovalRow({ label, value, tone = "default" }: ApprovalRowProps) {
  const valueClass = {
    default: "text-white/60",
    success: "text-success",
    brand: "text-brand-soft",
  }[tone];

  return (
    <div className="grid min-h-15 grid-cols-[5.75rem_minmax(0,1fr)] items-center gap-3 border-t border-white/8 px-4 sm:px-5">
      <dt className="font-mono text-[9px] tracking-[0.1em] text-white/28 uppercase">{label}</dt>
      <dd className={`truncate font-mono text-[10px] ${valueClass}`}>{value}</dd>
    </div>
  );
}

function DiffLine({ children, kind = "context" }: { children: string; kind?: "add" | "context" | "remove" }) {
  const styles = {
    add: "bg-success/[0.06] text-success/80 before:text-success",
    context: "text-white/36 before:text-white/18",
    remove: "bg-critical/[0.05] text-critical/68 before:text-critical",
  }[kind];
  const marker = kind === "add" ? "+" : kind === "remove" ? "−" : " ";

  return (
    <div className={`relative min-h-8 py-1.5 pr-4 pl-12 font-mono text-[10px] leading-5 ${styles}`}>
      <span aria-hidden="true" className="absolute top-1.5 left-5">
        {marker}
      </span>
      {children}
    </div>
  );
}

export function Approval() {
  return (
    <figure className="overflow-hidden border border-white/10 bg-[#090909]">
      <div className="flex min-h-14 items-center justify-between gap-4 border-b border-white/8 px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <p className="text-xs leading-5 text-white/76 sm:text-sm">
            Rollback mobile-money-amount-feature
          </p>
          <p className="mt-0.5 truncate font-mono text-[9px] tracking-[0.08em] text-white/28">
            histograph/rollback-hg-184
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 border border-success/28 px-3 py-1.5 font-mono text-[9px] tracking-[0.08em] text-success uppercase">
          <span aria-hidden="true" className="size-1.5 bg-success" />
          Approved
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(15rem,0.75fr)]">
        <div className="min-w-0">
          <div className="flex min-h-12 items-center justify-between border-b border-white/8 px-4 font-mono text-[9px] text-white/28 sm:px-5">
            <span>demo/deployment-feature-release.yaml</span>
            <span className="hidden sm:inline">1 file changed</span>
          </div>
          <div className="py-4 sm:py-5">
            <DiffLine>spec:</DiffLine>
            <DiffLine>  features:</DiffLine>
            <DiffLine>    - name: mobile-money-amount-feature</DiffLine>
            <DiffLine kind="remove">      version: v2</DiffLine>
            <DiffLine kind="add">      version: v1</DiffLine>
            <DiffLine kind="remove">      scaleMultiplier: 100</DiffLine>
            <DiffLine kind="add">      scaleMultiplier: 1</DiffLine>
          </div>
          <div className="grid grid-cols-2 border-t border-white/8">
            <div className="px-4 py-4 sm:px-5">
              <p className="font-mono text-[9px] tracking-[0.1em] text-white/26 uppercase">
                Action
              </p>
              <p className="mt-2 text-sm text-white/62">Rollback feature</p>
            </div>
            <div className="border-l border-white/8 px-4 py-4 sm:px-5">
              <p className="font-mono text-[9px] tracking-[0.1em] text-white/26 uppercase">
                Target
              </p>
              <p className="mt-2 font-mono text-[11px] text-white/62">v1 · ×1</p>
            </div>
          </div>
        </div>

        <dl className="border-t border-white/8 bg-white/[0.012] lg:border-t-0 lg:border-l">
          <div className="flex min-h-12 items-center px-4 sm:px-5">
            <p className="font-mono text-[9px] tracking-[0.12em] text-white/30 uppercase">
              Approval record
            </p>
          </div>
          <ApprovalRow label="Proposed by" value="Histograph" tone="brand" />
          <ApprovalRow label="Approved by" value="risk-lead" />
          <ApprovalRow label="Proof" value="Signed merge" tone="success" />
          <ApprovalRow label="Merge commit" value="87ac2d1" />
          <div className="border-t border-white/8 px-4 py-4 sm:px-5">
            <div className="flex items-center justify-between gap-4">
              <span className="font-mono text-[9px] tracking-[0.1em] text-white/28 uppercase">
                Runtime state
              </span>
              <span className="font-mono text-[9px] tracking-[0.08em] text-brand-soft uppercase">
                Reconciling
              </span>
            </div>
            <div aria-hidden="true" className="mt-3 h-px overflow-hidden bg-white/8">
              <span className="block h-full w-2/3 bg-brand-soft" />
            </div>
            <p className="mt-3 text-xs leading-5 text-white/34">
              Desired state changed. Observed state is verified separately.
            </p>
          </div>
        </dl>
      </div>

      <figcaption className="sr-only">
        Histograph proposes a rollback by restoring the amount feature from version 2 with a scale
        multiplier of 100 to version 1 with a multiplier of 1. A signed merge records the approving
        engineer, while runtime reconciliation remains a separate state.
      </figcaption>
    </figure>
  );
}
