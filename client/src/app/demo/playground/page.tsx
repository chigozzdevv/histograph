import type { Metadata } from "next";

import { Playground } from "@/components/demo/playground";
import {
  getDemoScenarioSnapshot,
  getDeployments,
  getOverview,
} from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Playground — Histograph",
  description: "Compare production model releases without recording telemetry.",
};

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type PlaygroundPageProps = {
  searchParams: Promise<{
    deployment?: string | string[];
    run?: string | string[];
  }>;
};

export default async function PlaygroundPage({
  searchParams,
}: PlaygroundPageProps) {
  const [deployments, overview, query] = await Promise.all([
    getDeployments(),
    getOverview(),
    searchParams,
  ]);
  const requestedRunId = Array.isArray(query.run) ? query.run[0] : query.run;
  const validRunId = requestedRunId && uuidPattern.test(requestedRunId) ? requestedRunId : null;
  const initialScenario = validRunId
    ? await getDemoScenarioSnapshot(validRunId)
    : null;
  const requestedDeploymentId = Array.isArray(query.deployment)
    ? query.deployment[0]
    : query.deployment;
  const initialDeploymentId = deployments.some(
    (deployment) => deployment.id === requestedDeploymentId,
  )
    ? requestedDeploymentId
    : initialScenario?.run.deployment_id ?? deployments[0]?.id;

  return (
    <Playground
      deployments={deployments}
      initialScenario={initialScenario}
      initialDeploymentId={initialDeploymentId}
      latestRun={overview.latest_demo_run}
    />
  );
}
