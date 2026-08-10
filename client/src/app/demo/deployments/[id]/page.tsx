import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DeploymentDetail } from "@/components/demo/deployments/detail";
import { getDeployment } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Deployment — Histograph",
  description: "Histograph deployment state and release traffic.",
};

export default async function DeploymentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const deployment = await getDeployment(id);

  if (!deployment) notFound();

  return <DeploymentDetail deployment={deployment} />;
}
