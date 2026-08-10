import type { Deployment, Incident, JsonValue } from "@/lib/histograph-api";

function asObject(value: JsonValue | undefined) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function textValue(value: JsonValue | undefined) {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function investigationContext(incident: Incident | null) {
  const investigation = asObject(incident?.evidence?.investigation);
  const lineage = asObject(investigation?.lineage);
  const upstream = Array.isArray(lineage?.upstream)
    ? lineage.upstream.map((item) => asObject(item)).find(Boolean)
    : null;
  const rootCause = asObject(investigation?.root_cause);

  return {
    hasEvidence: Boolean(upstream || rootCause),
    name: textValue(rootCause?.asset_name) ?? textValue(upstream?.name),
    meta:
      textValue(rootCause?.version) ??
      textValue(upstream?.type)?.toLowerCase().replaceAll("_", " "),
  };
}

function Node({
  eyebrow,
  label,
  meta,
  tone = "neutral",
}: {
  eyebrow: string;
  label: string;
  meta?: string;
  tone?: "neutral" | "violet" | "green";
}) {
  const toneClass = {
    neutral: "border-white/16 text-white/72",
    violet: "border-brand-soft/60 text-brand-soft",
    green: "border-success/55 text-success",
  }[tone];

  return (
    <div className="min-w-0 flex-1">
      <p className="mb-3 font-mono text-[9px] tracking-[0.13em] text-white/28 uppercase">
        {eyebrow}
      </p>
      <div className={`min-h-20 border bg-[#0b0b0b] px-4 py-4 ${toneClass}`}>
        <p className="truncate font-mono text-[11px]">{label}</p>
        {meta ? <p className="mt-2 font-mono text-[9px] text-white/26">{meta}</p> : null}
      </div>
    </div>
  );
}

function Connector() {
  return (
    <div aria-hidden="true" className="mt-10 flex w-10 shrink-0 items-center sm:w-15">
      <span className="h-px flex-1 bg-white/14" />
      <span className="size-1.5 rotate-45 border-t border-r border-white/26" />
    </div>
  );
}

export function Lineage({
  deployment,
  incident,
}: {
  deployment: Deployment | undefined;
  incident: Incident | null;
}) {
  const feature = deployment?.manifest.spec.features[0];
  const context = investigationContext(incident);
  const upstreamLabel =
    context.name ?? feature?.name.replace("mobile-money-", "").replaceAll("-", " ");
  const modelLabel = deployment?.model.replace("mobile-money-", "").replaceAll("-", " ");
  const modelTask = deployment?.manifest.spec.model.task?.replaceAll("_", " ");

  return (
    <section className="dashboard-register min-w-0 bg-[#0a0a0a]" id="integrations">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">Lineage</h2>
        <span className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
          {context.hasEvidence ? "DataHub evidence" : "Configured path"}
        </span>
      </div>
      <div className="border-t border-white/8 px-5 py-8 sm:px-6">
        <div className="flex items-start overflow-x-auto pb-1">
          <Node
            eyebrow={context.hasEvidence ? "Upstream" : "Feature"}
            label={upstreamLabel ?? "No upstream asset"}
            meta={context.meta ?? feature?.version}
            tone="violet"
          />
          <Connector />
          <Node eyebrow="Model" label={modelLabel ?? "No model"} meta={modelTask} />
          <Connector />
          <Node
            eyebrow="Deployment"
            label={deployment?.environment ?? "No deployment"}
            meta={
              deployment?.manifest.spec.candidate?.version ?? deployment?.manifest.spec.stable.version
            }
            tone="green"
          />
        </div>
      </div>
    </section>
  );
}
