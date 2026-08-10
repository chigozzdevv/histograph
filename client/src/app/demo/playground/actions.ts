"use server";

import {
  runPlayground,
  type ComparisonResult,
  type JsonObject,
  type PredictionResult,
} from "@/lib/histograph-api";

export type PlaygroundMode = "compare" | "predict";

export type PlaygroundActionState =
  | { status: "idle" }
  | {
      status: "success";
      mode: "compare";
      deploymentId: string;
      result: ComparisonResult;
    }
  | {
      status: "success";
      mode: "predict";
      deploymentId: string;
      result: PredictionResult;
    }
  | {
      status: "error";
      mode: PlaygroundMode;
      deploymentId: string;
      message: string;
    };

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isPredictionResult(value: unknown): value is PredictionResult {
  if (typeof value !== "object" || value === null) return false;

  const result = value as Record<string, unknown>;
  return (
    typeof result.prediction_id === "string" &&
    typeof result.model === "string" &&
    typeof result.version === "string" &&
    typeof result.deployment === "string" &&
    typeof result.score === "number" &&
    typeof result.predicted_class === "string" &&
    typeof result.threshold === "number" &&
    typeof result.observed_at === "string"
  );
}

function isComparisonResult(value: unknown): value is ComparisonResult {
  if (typeof value !== "object" || value === null) return false;

  const result = value as Record<string, unknown>;
  return (
    isPredictionResult(result.stable) &&
    isPredictionResult(result.candidate) &&
    result.telemetry_recorded === false
  );
}

function messageFrom(error: unknown) {
  const message = error instanceof Error ? error.message : "The Playground request failed.";
  return message.slice(0, 300);
}

export async function executePlayground(
  _previousState: PlaygroundActionState,
  formData: FormData,
): Promise<PlaygroundActionState> {
  const deploymentId = formData.get("deploymentId");
  const modeValue = formData.get("mode");
  const inputValue = formData.get("input");
  const mode: PlaygroundMode = modeValue === "predict" ? "predict" : "compare";

  if (typeof deploymentId !== "string" || !uuidPattern.test(deploymentId)) {
    return {
      status: "error",
      mode,
      deploymentId: typeof deploymentId === "string" ? deploymentId : "",
      message: "Select a live deployment before running the Playground.",
    };
  }

  if (modeValue !== "compare" && modeValue !== "predict") {
    return {
      status: "error",
      mode,
      deploymentId,
      message: "Choose Compare or Predict.",
    };
  }

  if (typeof inputValue !== "string" || inputValue.length > 250_000) {
    return {
      status: "error",
      mode,
      deploymentId,
      message: "Input must be JSON smaller than 250 KB.",
    };
  }

  let input: JsonObject;
  try {
    const parsed = JSON.parse(inputValue) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("Input must be a JSON object.");
    }
    input = parsed as JsonObject;
  } catch (error) {
    return {
      status: "error",
      mode,
      deploymentId,
      message: error instanceof SyntaxError ? "Input is not valid JSON." : messageFrom(error),
    };
  }

  try {
    const result = await runPlayground(deploymentId, mode, input);

    if (mode === "compare") {
      if (!isComparisonResult(result)) {
        throw new Error("The runtime returned an invalid comparison response.");
      }
      return { status: "success", mode, deploymentId, result };
    }

    if (!isPredictionResult(result)) {
      throw new Error("The runtime returned an invalid prediction response.");
    }
    return { status: "success", mode, deploymentId, result };
  } catch (error) {
    return {
      status: "error",
      mode,
      deploymentId,
      message: messageFrom(error),
    };
  }
}
