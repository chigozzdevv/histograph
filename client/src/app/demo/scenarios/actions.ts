"use server";

import {
  resetDemoScenario,
  startDemoScenario,
  type DemoScenarioReset,
} from "@/lib/histograph-api";

export type StartScenarioActionState =
  | { status: "idle" }
  | { status: "success"; runId: string }
  | { status: "error"; message: string };

export type ResetScenarioActionState =
  | { status: "idle" }
  | { status: "success"; reset: DemoScenarioReset }
  | { status: "error"; message: string };

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function messageFrom(error: unknown) {
  const message = error instanceof Error ? error.message : "The controlled scenario request failed.";
  return message.slice(0, 300);
}

export async function startControlledScenario(
  _previousState: StartScenarioActionState,
  formData: FormData,
): Promise<StartScenarioActionState> {
  const deploymentId = formData.get("deploymentId");
  if (typeof deploymentId !== "string" || !uuidPattern.test(deploymentId)) {
    return { status: "error", message: "A live deployment is required." };
  }

  try {
    const run = await startDemoScenario(deploymentId);
    return { status: "success", runId: run.id };
  } catch (error) {
    return { status: "error", message: messageFrom(error) };
  }
}

export async function resetControlledScenario(
  _previousState: ResetScenarioActionState,
  formData: FormData,
): Promise<ResetScenarioActionState> {
  const runId = formData.get("runId");
  if (typeof runId !== "string" || !uuidPattern.test(runId)) {
    return { status: "error", message: "A completed scenario run is required." };
  }

  try {
    const reset = await resetDemoScenario(runId);
    return { status: "success", reset };
  } catch (error) {
    return { status: "error", message: messageFrom(error) };
  }
}
