import type { Run, RunRequest } from "@/lib/types";

const apiUrl = process.env.NEXT_PUBLIC_HISTOGRAPH_API_URL ?? "http://localhost:8000";

export async function getRuns(): Promise<Run[]> {
  const response = await fetch(`${apiUrl}/v1/runs`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load runs: ${response.status}`);
  }
  const payload = (await response.json()) as { items: Run[] };
  return payload.items;
}

export async function getRun(runId: string): Promise<Run> {
  const response = await fetch(`${apiUrl}/v1/runs/${runId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(response.status === 404 ? "Run not found" : "Unable to load run");
  }
  return (await response.json()) as Run;
}

export async function createRun(request: RunRequest): Promise<Run> {
  const response = await fetch(`${apiUrl}/v1/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Unable to create run: ${response.status}`);
  }
  return (await response.json()) as Run;
}
