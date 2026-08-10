import Link from "next/link";

import { ArrowUpRightIcon } from "@/components/demo/icons";
import { Status } from "@/components/demo/status";
import {
  deploymentTraffic,
  findObservedRelease,
  TrafficSplit,
} from "@/components/demo/deployments/traffic";
import type { Deployment, JsonObject, JsonValue } from "@/lib/histograph-api";

function syncState(status: Deployment["sync_status"]) {
  if (status === "in_sync") return { label: "In sync", tone: "success" as const };
  if (status === "out_of_sync") return { label: "Out of sync", tone: "warning" as const };
  return { label: "Desired", tone: "neutral" as const };
}

function releaseTone(status: string | undefined) {
  if (status === "active" || status === "monitoring") return "success" as const;
  if (status === "stopped" || status === "rolled_back") return "neutral" as const;
  return "neutral" as const;
}

function readable(value: string | undefined) {
  return value ? value.replaceAll("_", " ") : "Not observed";
}

function formatDate(value: string | null) {
  if (!value) return "Not observed";
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

function objectValue(value: JsonValue | undefined): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}

function schemaCount(schema: JsonObject | null | undefined, field: "properties" | "required") {
  if (!schema) return 0;
  const value = schema[field];
  if (field === "required") return Array.isArray(value) ? value.length : 0;
  return Object.keys(objectValue(value) ?? {}).length;
}

function ReleaseRow({
  label,
  version,
  traffic,
  observedStatus,
}: {
  label: string;
  version: string;
  traffic: number;
  observedStatus?: string;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-5 border-t border-white/8 px-5 py-4 sm:px-6">
      <div className="min-w-0">
        <p className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
          {label}
        </p>
        <p className="mt-2 text-sm text-white/78">{version}</p>
      </div>
      <div className="flex items-center gap-6">
        <p className="font-mono text-xs text-white/52">{traffic}%</p>
        <Status
          label={readable(observedStatus)}
          tone={releaseTone(observedStatus)}
        />
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
        {label}
      </p>
      <div className="mt-2 truncate text-sm text-white/68">{value}</div>
    </div>
  );
}

function SourceLink({ href, value }: { href: string | null | undefined; value: string }) {
  if (!href) return value;

  return (
    <a
      className="inline-flex max-w-full items-center gap-1.5 text-white/68 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      href={href}
      rel="noopener noreferrer"
      target="_blank"
      title={value}
    >
      <span className="truncate">{value}</span>
      <ArrowUpRightIcon className="size-3.5 shrink-0" />
    </a>
  );
}

export function DeploymentDetail({ deployment }: { deployment: Deployment }) {
  const spec = deployment.manifest.spec;
  const traffic = deploymentTraffic(deployment);
  const stableObserved = findObservedRelease(deployment, spec.stable.version);
  const candidateObserved = spec.candidate
    ? findObservedRelease(deployment, spec.candidate.version)
    : undefined;
  const sync = syncState(deployment.sync_status);
  const source =
    deployment.repository_owner && deployment.repository_name
      ? `${deployment.repository_owner}/${deployment.repository_name}`
      : "Not connected";
  const inputFields = schemaCount(deployment.input_schema, "properties");
  const requiredFields = schemaCount(deployment.input_schema, "required");
  const outputFields = schemaCount(deployment.output_schema, "properties");

  return (
    <div className="mx-auto w-full max-w-400 px-5 py-7 sm:px-7 sm:py-9 lg:px-9 lg:py-10">
      <Link
        className="text-xs text-white/36 transition-colors hover:text-white/72 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        href="/demo/deployments"
      >
        ← Deployments
      </Link>

      <div className="mt-6 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <h1 className="break-words text-[1.65rem] leading-[1.05] font-normal tracking-[-0.035em] text-white">
              {deployment.deployment}
            </h1>
            <Status label={sync.label} tone={sync.tone} />
          </div>
          <p className="mt-2 font-mono text-[11px] text-white/32">{deployment.model}</p>
        </div>

        <Link
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 border border-white/14 px-4 text-sm text-white/72 transition-colors hover:border-white/28 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          href={`/demo/playground?deployment=${deployment.id}`}
        >
          Open in playground
          <ArrowUpRightIcon className="size-4" />
        </Link>
      </div>

      <div className="mt-7 overflow-hidden border border-white/10 bg-[#0a0a0a]">
        <div className="grid lg:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.75fr)]">
          <section>
            <div className="flex h-14 items-center justify-between px-5 sm:px-6">
              <h2 className="text-sm font-medium text-white/78">Traffic</h2>
              <span className="font-mono text-[10px] tracking-[0.1em] text-white/28 uppercase">
                {traffic.source}
              </span>
            </div>
            <div className="border-t border-white/8 px-5 py-5 sm:px-6">
              <TrafficSplit candidate={traffic.candidate} stable={traffic.stable} />
            </div>
            <ReleaseRow
              label="Stable"
              observedStatus={stableObserved?.status}
              traffic={traffic.stable.trafficPercentage}
              version={spec.stable.version}
            />
            {spec.candidate ? (
              <ReleaseRow
                label="Candidate"
                observedStatus={candidateObserved?.status}
                traffic={traffic.candidate?.trafficPercentage ?? 0}
                version={spec.candidate.version}
              />
            ) : null}
          </section>

          <section className="border-t border-white/10 lg:border-t-0 lg:border-l">
            <div className="flex h-14 items-center px-5 sm:px-6">
              <h2 className="text-sm font-medium text-white/78">Runtime</h2>
            </div>
            <div className="grid gap-6 border-t border-white/8 px-5 py-5 sm:grid-cols-2 sm:px-6 lg:grid-cols-1">
              <Fact label="Provider" value={deployment.provider} />
              <Fact label="Environment" value={deployment.environment} />
              <Fact label="Observed" value={formatDate(deployment.observed_at)} />
              <Fact
                label="Revision"
                value={
                  <span title={deployment.desired_revision}>
                    {deployment.desired_revision.slice(0, 12)}
                  </span>
                }
              />
            </div>
          </section>
        </div>

        <section className="border-t border-white/10">
          <div className="flex h-14 items-center justify-between px-5 sm:px-6">
            <h2 className="text-sm font-medium text-white/78">Features</h2>
            <span className="font-mono text-[10px] tracking-[0.1em] text-white/26 uppercase">
              {spec.features.length}
            </span>
          </div>
          {spec.features.length > 0 ? (
            <div className="border-t border-white/8">
              {spec.features.map((feature) => {
                const observed = deployment.observed_state?.features?.[feature.assetUrn];

                return (
                  <div
                    className="grid gap-4 border-b border-white/8 px-5 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_8rem_9rem] sm:items-center sm:px-6"
                    key={feature.assetUrn}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-white/72">{feature.name}</p>
                      <p className="mt-1 truncate font-mono text-[10px] text-white/26">
                        {feature.assetUrn}
                      </p>
                    </div>
                    <p className="font-mono text-xs text-white/46">{feature.version}</p>
                    <Status
                      label={readable(observed?.status)}
                      tone={observed?.status === "applied" ? "success" : "neutral"}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="border-t border-white/8 px-6 py-8 text-sm text-white/34">
              No managed features.
            </p>
          )}
        </section>

        <div className="grid border-t border-white/10 lg:grid-cols-2">
          <section>
            <div className="flex h-14 items-center px-5 sm:px-6">
              <h2 className="text-sm font-medium text-white/78">Contract</h2>
            </div>
            <div className="grid grid-cols-3 gap-5 border-t border-white/8 px-5 py-5 sm:px-6">
              <Fact label="Inputs" value={inputFields || "—"} />
              <Fact label="Required" value={requiredFields || "—"} />
              <Fact label="Outputs" value={outputFields || "—"} />
            </div>
            <div className="border-t border-white/8 px-5 py-4 sm:px-6">
              <p className="text-xs text-white/40">
                {deployment.examples?.length ?? 0} examples
              </p>
            </div>
          </section>

          <section className="border-t border-white/10 lg:border-t-0 lg:border-l">
            <div className="flex h-14 items-center px-5 sm:px-6">
              <h2 className="text-sm font-medium text-white/78">Source</h2>
            </div>
            <div className="grid gap-6 border-t border-white/8 px-5 py-5 sm:grid-cols-2 sm:px-6">
              <Fact
                label="Repository"
                value={
                  <SourceLink
                    href={deployment.source_links?.repository}
                    value={source}
                  />
                }
              />
              <Fact
                label="Branch"
                value={
                  <SourceLink
                    href={deployment.source_links?.branch}
                    value={deployment.branch ?? "—"}
                  />
                }
              />
              <div className="sm:col-span-2">
                <Fact
                  label="Manifest"
                  value={
                    <SourceLink
                      href={deployment.source_links?.manifest}
                      value={deployment.manifest_path ?? "—"}
                    />
                  }
                />
              </div>
              <div className="sm:col-span-2">
                <Fact
                  label="DataHub"
                  value={
                    <SourceLink
                      href={deployment.source_links?.datahub}
                      value={deployment.datahub_model_urn}
                    />
                  }
                />
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
