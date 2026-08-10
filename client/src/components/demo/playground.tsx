"use client";

import { useActionState, useState } from "react";

import {
  executePlayground,
  type PlaygroundActionState,
  type PlaygroundMode,
} from "@/app/demo/playground/actions";
import { ScenarioControl } from "@/components/demo/scenario-control";
import { ScenarioRun } from "@/components/demo/scenario-run";
import type {
  ComparisonResult,
  DemoScenarioRun,
  DemoScenarioSnapshot,
  Deployment,
  JsonObject,
  PredictionResult,
} from "@/lib/histograph-api";

const initialState: PlaygroundActionState = { status: "idle" };

function prettyInput(input: JsonObject | undefined) {
  return JSON.stringify(input ?? {}, null, 2);
}

function formatValue(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

function PredictionCard({
  label,
  result,
  tone = "neutral",
}: {
  label: string;
  result: PredictionResult;
  tone?: "neutral" | "brand";
}) {
  return (
    <article className="min-w-0 p-5 sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <p className="font-mono text-[10px] tracking-[0.15em] text-white/34 uppercase">
          {label}
        </p>
        <span
          className={`font-mono text-xs ${tone === "brand" ? "text-brand-soft" : "text-white/56"}`}
        >
          {result.version}
        </span>
      </div>

      <p className="mt-7 text-[2.35rem] leading-none tracking-[-0.045em] text-white">
        {formatValue(result.score)}
      </p>
      <p className="mt-2 text-xs text-white/34">Score</p>

      <dl className="mt-7 space-y-3 border-t border-white/8 pt-4 text-sm">
        <div className="flex items-center justify-between gap-4">
          <dt className="text-white/38">Class</dt>
          <dd className="truncate font-mono text-xs text-white/74">
            {result.predicted_class}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="text-white/38">Threshold</dt>
          <dd className="font-mono text-xs text-white/74">
            {formatValue(result.threshold)}
          </dd>
        </div>
      </dl>
    </article>
  );
}

function ComparisonResultView({ result }: { result: ComparisonResult }) {
  return (
    <div className="grid sm:grid-cols-2 sm:divide-x sm:divide-white/10">
      <PredictionCard label="Stable" result={result.stable} />
      <PredictionCard label="Candidate" result={result.candidate} tone="brand" />
    </div>
  );
}

function PredictionResultView({ result }: { result: PredictionResult }) {
  return <PredictionCard label="Production route" result={result} tone="brand" />;
}

function EmptyResult({ mode }: { mode: PlaygroundMode }) {
  return (
    <div className="dashboard-register flex min-h-105 items-center justify-center px-8 text-center">
      <div className="max-w-70 bg-midnight px-4 py-3">
        <p className="text-sm text-white/55">
          {mode === "compare"
            ? "Run a comparison to inspect both releases."
            : "Send an input through production routing."}
        </p>
      </div>
    </div>
  );
}

export function Playground({
  deployments,
  initialDeploymentId,
  initialScenario,
  latestRun,
}: {
  deployments: Deployment[];
  initialDeploymentId?: string;
  initialScenario: DemoScenarioSnapshot | null;
  latestRun: Omit<DemoScenarioRun, "result"> | null;
}) {
  const initialDeployment =
    deployments.find((item) => item.id === initialDeploymentId) ?? deployments[0];
  const [deploymentId, setDeploymentId] = useState(initialDeployment?.id ?? "");
  const [mode, setMode] = useState<PlaygroundMode>("compare");
  const deployment = deployments.find((item) => item.id === deploymentId);
  const [exampleIndex, setExampleIndex] = useState(0);
  const [input, setInput] = useState(() =>
    prettyInput(initialDeployment?.examples?.[0]?.input),
  );
  const [state, formAction, pending] = useActionState(executePlayground, initialState);

  const examples = deployment?.examples ?? [];
  const candidate = deployment?.manifest.spec.candidate;
  const compareUnavailable = mode === "compare" && !candidate;
  const canSubmit = Boolean(deployment && !compareUnavailable && input.trim());
  const currentState =
    state.status !== "idle" &&
    state.deploymentId === deploymentId &&
    state.mode === mode
      ? state
      : initialState;

  function selectDeployment(nextId: string) {
    const nextDeployment = deployments.find((item) => item.id === nextId);
    setDeploymentId(nextId);
    setExampleIndex(0);
    setInput(prettyInput(nextDeployment?.examples?.[0]?.input));
  }

  function selectExample(nextIndex: number) {
    setExampleIndex(nextIndex);
    setInput(prettyInput(examples[nextIndex]?.input));
  }

  return (
    <div className="mx-auto w-full max-w-400 px-5 py-7 sm:px-7 sm:py-9 lg:px-9 lg:py-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <h1 className="text-[1.65rem] leading-none font-normal tracking-[-0.035em] text-white">
          Playground
        </h1>
        <ScenarioControl
          canStart={Boolean(candidate && candidate.trafficPercentage > 0)}
          currentRunId={initialScenario?.run.id}
          deploymentId={deployment?.id}
          latestRun={latestRun}
        />
      </div>

      {initialScenario ? (
        <ScenarioRun initialSnapshot={initialScenario} />
      ) : (
        <div className="mt-7 overflow-hidden border border-white/10 bg-[#0a0a0a]">
        <div className="grid xl:grid-cols-[minmax(0,1.05fr)_minmax(24rem,0.95fr)]">
          <form
            action={formAction}
            className="min-w-0 p-5 sm:p-6 lg:p-7"
            onReset={(event) => event.preventDefault()}
          >
            <input name="mode" type="hidden" value={mode} />

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block min-w-0">
                <span className="font-mono text-[10px] tracking-[0.13em] text-white/34 uppercase">
                  Deployment
                </span>
                <select
                  className="mt-2 h-11 w-full border border-white/10 bg-midnight px-3 text-sm text-white/78 outline-none focus:border-brand/70"
                  name="deploymentId"
                  onChange={(event) => selectDeployment(event.target.value)}
                  value={deploymentId}
                >
                  {deployments.length ? null : <option value="">No deployments</option>}
                  {deployments.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.deployment}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block min-w-0">
                <span className="font-mono text-[10px] tracking-[0.13em] text-white/34 uppercase">
                  Example
                </span>
                <select
                  className="mt-2 h-11 w-full border border-white/10 bg-midnight px-3 text-sm text-white/78 outline-none focus:border-brand/70 disabled:text-white/28"
                  disabled={!examples.length}
                  onChange={(event) => selectExample(Number(event.target.value))}
                  value={exampleIndex}
                >
                  {examples.length ? null : <option value={0}>No examples</option>}
                  {examples.map((example, index) => (
                    <option key={example.id ?? index} value={index}>
                      {example.label ?? example.id ?? `Example ${index + 1}`}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <fieldset className="mt-6">
              <legend className="font-mono text-[10px] tracking-[0.13em] text-white/34 uppercase">
                Mode
              </legend>
              <div className="mt-2 grid grid-cols-2 border border-white/10 p-1">
                {(["compare", "predict"] as const).map((item) => {
                  const active = mode === item;
                  return (
                    <button
                      className={`h-10 px-3 text-sm transition-colors ${
                        active
                          ? "bg-white/[0.08] text-white"
                          : "text-white/38 hover:text-white/68"
                      }`}
                      key={item}
                      onClick={() => setMode(item)}
                      type="button"
                    >
                      {item === "compare" ? "Compare releases" : "Predict"}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <label className="mt-6 block">
              <span className="font-mono text-[10px] tracking-[0.13em] text-white/34 uppercase">
                Input
              </span>
              <textarea
                className="mt-2 min-h-88 w-full resize-y border border-white/10 bg-midnight p-4 font-mono text-xs leading-6 text-white/72 outline-none focus:border-brand/70"
                name="input"
                onChange={(event) => setInput(event.target.value)}
                spellCheck={false}
                value={input}
              />
            </label>

            {compareUnavailable ? (
              <p className="mt-3 text-xs text-white/36">
                This deployment has no candidate release to compare.
              </p>
            ) : null}

            {currentState.status === "error" ? (
              <p aria-live="polite" className="mt-3 text-sm text-critical" role="alert">
                {currentState.message}
              </p>
            ) : null}

            <button
              className="mt-6 inline-flex min-h-12 items-center justify-center bg-white px-5 text-sm font-medium text-[#111] transition-colors hover:bg-brand hover:text-white disabled:cursor-not-allowed disabled:bg-white/12 disabled:text-white/30"
              disabled={!canSubmit || pending}
              type="submit"
            >
              {pending
                ? "Running…"
                : mode === "compare"
                  ? "Compare releases"
                  : "Send prediction"}
            </button>
          </form>

          <section
            aria-live="polite"
            className="min-w-0 border-t border-white/10 bg-midnight xl:border-t-0 xl:border-l"
          >
            <div className="flex h-14 items-center justify-between border-b border-white/8 px-5 sm:px-6">
              <h2 className="text-sm font-medium text-white/72">Result</h2>
              {currentState.status === "success" ? (
                <span className="font-mono text-[10px] tracking-[0.12em] text-success uppercase">
                  Complete
                </span>
              ) : null}
            </div>

            {currentState.status === "success" && currentState.mode === "compare" ? (
              <ComparisonResultView result={currentState.result} />
            ) : currentState.status === "success" && currentState.mode === "predict" ? (
              <PredictionResultView result={currentState.result} />
            ) : (
              <EmptyResult mode={mode} />
            )}
          </section>
        </div>
        </div>
      )}
    </div>
  );
}
