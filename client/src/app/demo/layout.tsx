import { DemoShell } from "@/components/demo/shell";
import { getDeployments } from "@/lib/histograph-api";

export default async function DemoLayout({ children }: { children: React.ReactNode }) {
  const deployments = await getDeployments();
  const liveEnvironment = deployments[0]?.environment;
  const environment = liveEnvironment
    ? `${liveEnvironment.charAt(0).toUpperCase()}${liveEnvironment.slice(1)}`
    : "No environment";

  return <DemoShell environment={environment}>{children}</DemoShell>;
}
