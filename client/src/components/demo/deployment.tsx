import { Status } from "@/components/demo/status";
import type { Deployment } from "@/lib/histograph-api";

function syncState(status: Deployment["sync_status"]) {
  if (status === "in_sync") return { label: "In sync", tone: "success" as const };
  if (status === "out_of_sync") return { label: "Out of sync", tone: "warning" as const };
  return { label: "Desired", tone: "neutral" as const };
}

export function DeploymentPanel({ deployment }: { deployment: Deployment | undefined }) {
  const stable = deployment?.manifest.spec.stable;
  const candidate = deployment?.manifest.spec.candidate;
  const observedVersions = Object.values(deployment?.observed_state?.model_versions ?? {});
  const observedStable = observedVersions.find((release) => release.version === stable?.version);
  const observedCandidate = observedVersions.find((release) => release.version === candidate?.version);
  const hasRuntimeState = observedVersions.length > 0;
  const stableTraffic = observedStable?.traffic_percentage ?? stable?.trafficPercentage ?? 0;
  const candidateTraffic = observedCandidate?.traffic_percentage ?? candidate?.trafficPercentage ?? 0;
  const sync = deployment ? syncState(deployment.sync_status) : null;

  return (
    <section className="bg-[#0a0a0a]" id="deployments">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <h2 className="text-sm font-medium text-white/78">Deployment</h2>
        {sync ? <Status label={sync.label} tone={sync.tone} /> : null}
      </div>
      <div className="border-t border-white/8 px-5 py-5 sm:px-6">
        <p className="truncate text-base text-white/90">
          {deployment?.deployment ?? "No deployment"}
        </p>
        <p className="mt-1 truncate font-mono text-[11px] text-white/32">
          {deployment?.model ?? "—"}
        </p>

        <p className="mt-6 font-mono text-[9px] tracking-[0.12em] text-white/28 uppercase">
          {hasRuntimeState ? "Runtime traffic" : "Desired traffic"}
        </p>

        <div className="mt-3 flex h-2 overflow-hidden bg-white/6">
          <span
            className="bg-white/55"
            style={{ width: `${stableTraffic}%` }}
          />
          <span
            className="bg-brand-soft"
            style={{ width: `${candidateTraffic}%` }}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <p className="font-mono text-[10px] tracking-[0.12em] text-white/30 uppercase">
              Stable
            </p>
            <p className="mt-2 text-sm text-white/72">
              {stable?.version ?? "—"} <span className="text-white/34">·</span>{" "}
              {stableTraffic}%
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] tracking-[0.12em] text-white/30 uppercase">
              Candidate
            </p>
            <p className="mt-2 text-sm text-brand-soft">
              {candidate?.version ?? "—"} <span className="text-white/34">·</span>{" "}
              {candidateTraffic}%
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
