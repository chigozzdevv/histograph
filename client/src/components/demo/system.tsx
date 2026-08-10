import { Status } from "@/components/demo/status";
import type { Integrations } from "@/lib/histograph-api";

function SystemRow({
  name,
  available,
  detail,
}: {
  name: string;
  available: boolean;
  detail: string;
}) {
  return (
    <div className="flex min-h-16 items-center justify-between border-t border-white/8 px-5 sm:px-6">
      <div>
        <p className="text-sm text-white/72">{name}</p>
        <p className="mt-1 font-mono text-[10px] text-white/28">{detail}</p>
      </div>
      <Status
        label={available ? "Configured" : "Not configured"}
        tone={available ? "success" : "neutral"}
      />
    </div>
  );
}

export function SystemPanel({ integrations }: { integrations: Integrations }) {
  return (
    <section className="bg-[#0a0a0a]">
      <div className="flex h-14 items-center px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">System</h2>
      </div>
      <SystemRow
        available={integrations.datahub.configured}
        detail="Lineage + write-back"
        name="DataHub"
      />
      <SystemRow
        available={integrations.github.configured}
        detail="Deployment manifests"
        name="GitHub"
      />
      <SystemRow
        available={integrations.reference_runtime.control_configured}
        detail="Serving state"
        name="Runtime"
      />
    </section>
  );
}
