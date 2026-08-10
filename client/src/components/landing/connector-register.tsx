type ConnectorKind = "datahub" | "github" | "runtime";

type ConnectorRowProps = {
  detail: string;
  exchange: string;
  kind: ConnectorKind;
  name: string;
};

function ConnectorGlyph({ kind }: { kind: ConnectorKind }) {
  if (kind === "datahub") {
    return (
      <svg aria-hidden="true" className="size-5" fill="none" viewBox="0 0 20 20">
        <path d="M3.5 5.5h13v9h-13zM7 5.5v-2h6v2M7 14.5v2h6v-2" stroke="currentColor" />
        <path d="M7 8.5h6M7 11.5h6" stroke="currentColor" strokeOpacity=".55" />
      </svg>
    );
  }

  if (kind === "github") {
    return (
      <svg aria-hidden="true" className="size-5" fill="none" viewBox="0 0 20 20">
        <circle cx="6" cy="5" r="1.5" stroke="currentColor" />
        <circle cx="14" cy="10" r="1.5" stroke="currentColor" />
        <circle cx="6" cy="15" r="1.5" stroke="currentColor" />
        <path d="M6 6.5v7M7.5 5h1.75A4.75 4.75 0 0 1 14 9" stroke="currentColor" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" className="size-5" fill="none" viewBox="0 0 20 20">
      <path d="M2.5 10h3l2-5 3.5 10 2.5-6 1.5 1h2.5" stroke="currentColor" strokeLinejoin="miter" />
    </svg>
  );
}

function ConnectorRow({ detail, exchange, kind, name }: ConnectorRowProps) {
  return (
    <div className="grid min-h-24 grid-cols-[minmax(0,1fr)_auto] border-t border-white/8 sm:grid-cols-[9.5rem_minmax(0,1fr)_9.5rem]">
      <div className="flex items-center gap-3 px-4 py-4 text-white/64 sm:px-5">
        <span className="flex size-9 shrink-0 items-center justify-center border border-white/14">
          <ConnectorGlyph kind={kind} />
        </span>
        <div>
          <p className="text-sm text-white/72">{name}</p>
          <p className="mt-1 font-mono text-[9px] tracking-[0.08em] text-white/26 uppercase">
            Configured
          </p>
        </div>
      </div>

      <div className="relative col-span-2 row-start-2 flex min-w-0 items-center border-t border-white/8 px-4 py-4 sm:col-span-1 sm:row-auto sm:border-t-0 sm:border-l sm:px-6 sm:py-5">
        <div aria-hidden="true" className="absolute top-1/2 right-6 left-6 h-px -translate-y-1/2 bg-white/10" />
        <span aria-hidden="true" className="absolute top-1/2 left-6 size-1.5 -translate-y-1/2 bg-brand-soft" />
        <div className="relative z-10 mx-auto max-w-full bg-[#090909] px-4 text-center">
          <p className="font-mono text-[10px] leading-4 text-white/62">{exchange}</p>
          <p className="mt-1 font-mono text-[9px] leading-4 text-white/32">{detail}</p>
        </div>
        <span aria-hidden="true" className="absolute top-1/2 right-6 size-1.5 -translate-y-1/2 bg-success" />
      </div>

      <div className="col-start-2 row-start-1 flex items-center justify-between gap-4 border-l border-white/8 px-4 py-4 sm:col-auto sm:row-auto sm:border-l sm:px-5">
        <div>
          <p className="font-mono text-[9px] tracking-[0.1em] text-white/26 uppercase">
            Destination
          </p>
          <p className="mt-2 font-mono text-[10px] text-white/58">Incident record</p>
        </div>
        <span aria-hidden="true" className="size-2 border border-success bg-success/10" />
      </div>
    </div>
  );
}

export function ConnectorRegister() {
  return (
    <figure className="overflow-hidden border border-white/10 bg-[#090909]">
      <div className="grid min-h-14 grid-cols-[1fr_auto] items-center gap-5 px-4 sm:px-6">
        <div>
          <p className="text-sm text-white/72">Connector register</p>
          <p className="mt-0.5 font-mono text-[9px] tracking-[0.08em] text-white/28 uppercase">
            Existing systems stay authoritative
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-success uppercase">
          <span aria-hidden="true" className="size-1.5 bg-success" />
          3 connected
        </div>
      </div>

      <ConnectorRow
        detail="entity + upstream/downstream lineage"
        exchange="Lineage context"
        kind="datahub"
        name="DataHub"
      />
      <ConnectorRow
        detail="manifest + signed merge + deploy status"
        exchange="Desired state + approval"
        kind="github"
        name="GitHub"
      />
      <ConnectorRow
        detail="predictions + outcomes + runtime state"
        exchange="Telemetry + runtime state"
        kind="runtime"
        name="Runtime"
      />

      <figcaption className="sr-only">
        Histograph connects DataHub lineage context, GitHub deployment state and approvals, and the
        organization&apos;s model runtime telemetry and observed state into one incident record without
        replacing any of those systems.
      </figcaption>
    </figure>
  );
}
