import { Activity } from "@/components/demo/activity";
import { DeploymentPanel } from "@/components/demo/deployment";
import { Health } from "@/components/demo/health";
import { IncidentPanel } from "@/components/demo/incident";
import { Lineage } from "@/components/demo/lineage";
import { SystemPanel } from "@/components/demo/system";
import type { DashboardData } from "@/lib/histograph-api";

export function Overview({ data }: { data: DashboardData }) {
  const deployment = data.deployments[0];
  const incident =
    data.incidents.find((item) => ["open", "investigating"].includes(item.status)) ??
    data.overview.latest_incident;
  const monitor =
    data.monitors.find((item) => item.id === incident?.monitor_id) ?? data.monitors[0];

  return (
    <div className="mx-auto w-full max-w-400 px-5 py-7 sm:px-7 sm:py-9 lg:px-9 lg:py-10">
      <h1 className="text-[1.65rem] leading-none font-normal tracking-[-0.035em] text-white">
        Overview
      </h1>

      <div className="mt-7 overflow-hidden border border-white/10">
        <div className="grid xl:grid-cols-[minmax(0,1.7fr)_minmax(20rem,0.8fr)]">
          <Health incident={incident} monitor={monitor} runs={data.monitorRuns} />
          <div className="border-t border-white/10 xl:border-t-0 xl:border-l">
            <DeploymentPanel deployment={deployment} />
            <IncidentPanel incident={incident} />
          </div>
        </div>

        <div className="grid border-t border-white/10 xl:grid-cols-[minmax(0,1.7fr)_minmax(20rem,0.8fr)]">
          <Lineage deployment={deployment} incident={incident} />
          <div className="border-t border-white/10 xl:border-t-0 xl:border-l">
            <SystemPanel integrations={data.integrations} />
          </div>
        </div>

        <div className="border-t border-white/10">
          <Activity items={data.activity} />
        </div>
      </div>
    </div>
  );
}
