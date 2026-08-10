import type { Metadata } from "next";

import {
  ReadOnlyPage,
  ReadOnlySection,
} from "@/components/demo/read-only-page";
import { Status } from "@/components/demo/status";
import { getIntegrations } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Integrations — Histograph",
  description: "Read-only integration configuration for Histograph's demo environment.",
};

function ConfigurationStatus({ configured }: { configured: boolean }) {
  return <Status label={configured ? "Configured" : "Not configured"} tone="neutral" />;
}

export default async function IntegrationsPage() {
  const integrations = await getIntegrations();

  return (
    <ReadOnlyPage
      action={
        <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
          Configuration only
        </span>
      }
      title="Integrations"
    >
      <div className="grid gap-5 xl:grid-cols-3">
          <ReadOnlySection
            meta={<ConfigurationStatus configured={integrations.datahub.configured} />}
            title="DataHub"
          >
            <div className="px-5 py-5 sm:px-6">
              <p className="text-sm leading-6 text-white/52">
                Metadata and lineage endpoint configuration for incident investigation.
              </p>
              <div className="mt-6 space-y-4">
                <div>
                  <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Endpoint</p>
                  <p className="mt-1.5 text-xs text-white/58">
                    {integrations.datahub.configured ? "Configured" : "Not configured"}
                  </p>
                </div>
                <div>
                  <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">Write-back</p>
                  <p className="mt-1.5 text-xs text-white/58">
                    {integrations.datahub.write_back_enabled ? "Enabled" : "Disabled"}
                  </p>
                </div>
              </div>
            </div>
          </ReadOnlySection>

          <ReadOnlySection
            meta={<ConfigurationStatus configured={integrations.github.configured} />}
            title="GitHub"
          >
            <div className="px-5 py-5 sm:px-6">
              <p className="text-sm leading-6 text-white/52">
                GitOps deployment manifests and recorded rollback pull-request integration.
              </p>
              <div className="mt-6">
                <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
                  Connections
                </p>
                {integrations.github.connections.length === 0 ? (
                  <p className="mt-2 text-xs text-white/38">No repository connections reported.</p>
                ) : (
                  <div className="mt-2 space-y-3">
                    {integrations.github.connections.map((connection) => (
                      <div className="border border-white/8 px-3 py-3" key={connection.id}>
                        <div className="flex items-start justify-between gap-3">
                          <p className="min-w-0 truncate font-mono text-[10px] text-white/58">
                            {connection.repository_owner}/{connection.repository_name}
                          </p>
                          <Status
                            label={connection.enabled ? "Enabled" : "Disabled"}
                            tone="neutral"
                          />
                        </div>
                        {connection.last_error ? (
                          <p className="mt-2 text-[11px] leading-5 text-critical/76">
                            {connection.last_error}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </ReadOnlySection>

          <ReadOnlySection
            meta={
              <ConfigurationStatus configured={integrations.reference_runtime.control_configured} />
            }
            title="Reference runtime"
          >
            <div className="px-5 py-5 sm:px-6">
              <p className="text-sm leading-6 text-white/52">
                Server-held control configuration for the isolated reference serving environment.
              </p>
              <div className="mt-6">
                <p className="font-mono text-[9px] tracking-[0.12em] text-white/26 uppercase">
                  Allowed hosts
                </p>
                {integrations.reference_runtime.allowed_hosts.length === 0 ? (
                  <p className="mt-2 text-xs text-white/38">No runtime hosts reported.</p>
                ) : (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {integrations.reference_runtime.allowed_hosts.map((host) => (
                      <span className="border border-white/8 px-2.5 py-1.5 font-mono text-[10px] text-white/46" key={host}>
                        {host}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </ReadOnlySection>
      </div>
    </ReadOnlyPage>
  );
}
