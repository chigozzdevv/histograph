import type { Metadata } from "next";

import { Playground } from "@/components/demo/playground";
import { getDeployments } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Playground — Histograph",
  description: "Compare production model releases without recording telemetry.",
};

type PlaygroundPageProps = {
  searchParams: Promise<{
    deployment?: string | string[];
  }>;
};

export default async function PlaygroundPage({
  searchParams,
}: PlaygroundPageProps) {
  const [deployments, query] = await Promise.all([
    getDeployments(),
    searchParams,
  ]);
  const requestedDeploymentId = Array.isArray(query.deployment)
    ? query.deployment[0]
    : query.deployment;
  const initialDeploymentId = deployments.some(
    (deployment) => deployment.id === requestedDeploymentId,
  )
    ? requestedDeploymentId
    : deployments[0]?.id;

  return (
    <Playground
      deployments={deployments}
      initialDeploymentId={initialDeploymentId}
    />
  );
}
