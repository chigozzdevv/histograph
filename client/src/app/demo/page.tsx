import type { Metadata } from "next";

import { Overview } from "@/components/demo/overview";
import { getDashboardData } from "@/lib/histograph-api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Overview — Histograph",
  description: "Histograph production ML overview.",
};

export default async function DemoPage() {
  const data = await getDashboardData();

  return <Overview data={data} />;
}
