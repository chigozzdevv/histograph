import Link from "next/link";

import { ArrowUpRightIcon } from "@/components/demo/icons";
import { Status } from "@/components/demo/status";
import {
  deploymentTraffic,
  TrafficSplit,
} from "@/components/demo/deployments/traffic";
import type { Deployment } from "@/lib/histograph-api";

function syncState(status: Deployment["sync_status"]) {
  if (status === "in_sync") return { label: "In sync", tone: "success" as const };
  if (status === "out_of_sync") return { label: "Out of sync", tone: "warning" as const };
  return { label: "Desired", tone: "neutral" as const };
}

function DeploymentRow({ deployment }: { deployment: Deployment }) {
  const traffic = deploymentTraffic(deployment);
  const sync = syncState(deployment.sync_status);

  return (
    <li>
      <Link
        className="group grid gap-5 border-t border-white/8 px-5 py-5 transition-colors hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:px-6 lg:grid-cols-[minmax(15rem,1.35fr)_minmax(13rem,0.9fr)_8rem_8rem_1.5rem] lg:items-center"
        href={`/demo/deployments/${deployment.id}`}
      >
        <div className="min-w-0">
          <p className="truncate text-sm text-white/88">{deployment.deployment}</p>
          <p className="mt-1 truncate font-mono text-[11px] text-white/32">
            {deployment.model}
          </p>
        </div>

        <div className="min-w-0">
          <TrafficSplit candidate={traffic.candidate} compact stable={traffic.stable} />
          <p className="mt-2 font-mono text-[10px] tracking-[0.08em] text-white/34 uppercase">
            {traffic.source} · {traffic.stable.version} {traffic.stable.trafficPercentage}%
            {traffic.candidate
              ? ` · ${traffic.candidate.version} ${traffic.candidate.trafficPercentage}%`
              : ""}
          </p>
        </div>

        <p className="text-sm text-white/54 capitalize">{deployment.environment}</p>
        <Status label={sync.label} tone={sync.tone} />
        <ArrowUpRightIcon className="hidden size-4 text-white/24 transition-colors group-hover:text-white/62 lg:block" />
      </Link>
    </li>
  );
}

export function DeploymentList({ deployments }: { deployments: Deployment[] }) {
  return (
    <div className="mx-auto w-full max-w-400 px-5 py-7 sm:px-7 sm:py-9 lg:px-9 lg:py-10">
      <div className="flex items-end justify-between gap-4">
        <h1 className="text-[1.65rem] leading-none font-normal tracking-[-0.035em] text-white">
          Deployments
        </h1>
        <p className="font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase">
          {deployments.length} {deployments.length === 1 ? "deployment" : "deployments"}
        </p>
      </div>

      <section className="mt-7 overflow-hidden border border-white/10 bg-[#0a0a0a]">
        <div className="hidden h-11 grid-cols-[minmax(15rem,1.35fr)_minmax(13rem,0.9fr)_8rem_8rem_1.5rem] items-center gap-5 px-6 font-mono text-[10px] tracking-[0.12em] text-white/28 uppercase lg:grid">
          <span>Deployment</span>
          <span>Traffic</span>
          <span>Environment</span>
          <span>State</span>
          <span />
        </div>

        {deployments.length > 0 ? (
          <ul>
            {deployments.map((deployment) => (
              <DeploymentRow deployment={deployment} key={deployment.id} />
            ))}
          </ul>
        ) : (
          <p className="border-t border-white/8 px-6 py-14 text-center text-sm text-white/34">
            No deployments found.
          </p>
        )}
      </section>
    </div>
  );
}
