import type { Deployment } from "@/lib/histograph-api";

type Release = {
  version: string;
  trafficPercentage: number;
};

export function findObservedRelease(deployment: Deployment, version: string) {
  return Object.values(deployment.observed_state?.model_versions ?? {}).find(
    (release) => release.version === version,
  );
}

export function deploymentTraffic(deployment: Deployment) {
  const desiredStable = deployment.manifest.spec.stable;
  const desiredCandidate = deployment.manifest.spec.candidate;
  const observedStable = findObservedRelease(deployment, desiredStable.version);
  const observedCandidate = desiredCandidate
    ? findObservedRelease(deployment, desiredCandidate.version)
    : undefined;
  const hasRuntimeTraffic = Boolean(
    observedStable && (!desiredCandidate || observedCandidate),
  );

  return {
    source: hasRuntimeTraffic ? ("Runtime" as const) : ("Desired" as const),
    stable: {
      version: desiredStable.version,
      trafficPercentage: hasRuntimeTraffic
        ? observedStable?.traffic_percentage ?? 0
        : desiredStable.trafficPercentage,
    },
    candidate: desiredCandidate
      ? {
          version: desiredCandidate.version,
          trafficPercentage: hasRuntimeTraffic
            ? observedCandidate?.traffic_percentage ?? 0
            : desiredCandidate.trafficPercentage,
        }
      : undefined,
  };
}

export function TrafficSplit({
  stable,
  candidate,
  compact = false,
}: {
  stable: Release;
  candidate?: Release;
  compact?: boolean;
}) {
  return (
    <div>
      <div
        aria-label={`${stable.version} ${stable.trafficPercentage}%${
          candidate ? `, ${candidate.version} ${candidate.trafficPercentage}%` : ""
        }`}
        className={`flex overflow-hidden bg-white/6 ${compact ? "h-1.5" : "h-2"}`}
        role="img"
      >
        <span
          className="bg-white/56"
          style={{ width: `${stable.trafficPercentage}%` }}
        />
        {candidate ? (
          <span
            className="bg-brand-soft"
            style={{ width: `${candidate.trafficPercentage}%` }}
          />
        ) : null}
      </div>

      {!compact ? (
        <div className="mt-4 flex items-center gap-6 text-xs">
          <span className="inline-flex items-center gap-2 text-white/52">
            <span className="size-1.5 bg-white/56" />
            {stable.version} · {stable.trafficPercentage}%
          </span>
          {candidate ? (
            <span className="inline-flex items-center gap-2 text-white/52">
              <span className="size-1.5 bg-brand-soft" />
              {candidate.version} · {candidate.trafficPercentage}%
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
