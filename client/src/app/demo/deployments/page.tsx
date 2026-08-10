import type { Metadata } from "next";

import { DeploymentList } from "@/components/demo/deployments/list";
import { getDeployments } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Deployments — Histograph",
  description: "Histograph managed model deployments.",
};

export default async function DeploymentsPage() {
  const deployments = await getDeployments();

  return <DeploymentList deployments={deployments} />;
}
