"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";

import {
  resetControlledScenario,
  startControlledScenario,
  type ResetScenarioActionState,
  type StartScenarioActionState,
} from "@/app/demo/scenarios/actions";
import { ArrowUpRightIcon } from "@/components/demo/icons";
import type { DemoScenarioRun } from "@/lib/histograph-api";

const initialStartState: StartScenarioActionState = { status: "idle" };
const initialResetState: ResetScenarioActionState = { status: "idle" };

export function ScenarioControl({
  deploymentId,
  canStart,
  latestRun,
  currentRunId,
}: {
  deploymentId?: string;
  canStart: boolean;
  latestRun: Omit<DemoScenarioRun, "result"> | null;
  currentRunId?: string;
}) {
  const router = useRouter();
  const [state, formAction, pending] = useActionState(
    startControlledScenario,
    initialStartState,
  );
  const [resetState, resetAction, resetPending] = useActionState(
    resetControlledScenario,
    initialResetState,
  );
  const activeRun = latestRun && !["resolved", "failed"].includes(latestRun.status);
  const runHref = (runId: string) => `/demo/playground?run=${encodeURIComponent(runId)}`;

  useEffect(() => {
    if (state.status === "success") router.push(runHref(state.runId));
  }, [router, state]);

  if (currentRunId) {
    return (
      <Link
        className="inline-flex h-10 items-center justify-center border border-white/14 px-4 text-sm text-white/68 transition-colors hover:border-white/28 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        href="/demo/playground"
      >
        Manual test
      </Link>
    );
  }

  if (activeRun) {
    return (
      <Link
        className="inline-flex h-10 items-center justify-center gap-2 border border-white/14 px-4 text-sm text-white/68 transition-colors hover:border-white/28 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        href={runHref(latestRun.id)}
      >
        View live run
        <ArrowUpRightIcon className="size-4" />
      </Link>
    );
  }

  if (!canStart) {
    if (!latestRun || activeRun) return null;

    if (resetState.status === "success") {
      return (
        <a
          className="inline-flex h-10 items-center justify-center gap-2 border border-white/14 px-4 text-sm text-white/68 transition-colors hover:border-white/28 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          href={resetState.reset.pull_request_url}
          rel="noopener noreferrer"
          target="_blank"
        >
          Review reset PR
          <ArrowUpRightIcon className="size-4" />
        </a>
      );
    }

    return (
      <form action={resetAction} className="relative">
        <input name="runId" type="hidden" value={latestRun.id} />
        <button
          className="inline-flex h-10 items-center justify-center border border-white/14 px-4 text-sm text-white/68 transition-colors hover:border-white/28 hover:text-white disabled:cursor-not-allowed disabled:text-white/24"
          disabled={resetPending}
          type="submit"
        >
          {resetPending ? "Opening…" : "Reset demo"}
        </button>
        {resetState.status === "error" ? (
          <span
            aria-live="polite"
            className="absolute top-full right-0 z-40 mt-2 w-72 border border-critical/30 bg-[#111] px-3 py-2 text-right text-xs text-critical shadow-2xl"
            role="alert"
          >
            {resetState.message}
          </span>
        ) : null}
      </form>
    );
  }

  return (
    <form action={formAction} className="relative">
      <input name="deploymentId" type="hidden" value={deploymentId} />
      <button
        className="inline-flex h-10 items-center justify-center bg-white px-4 text-sm font-medium text-[#111] transition-colors hover:bg-brand hover:text-white disabled:cursor-not-allowed disabled:bg-white/12 disabled:text-white/30"
        disabled={!deploymentId || pending}
        type="submit"
      >
        {pending ? "Starting…" : "Run controlled scenario"}
      </button>
      {state.status === "error" ? (
        <span
          aria-live="polite"
          className="absolute top-full right-0 z-40 mt-2 w-72 border border-critical/30 bg-[#111] px-3 py-2 text-right text-xs text-critical shadow-2xl"
          role="alert"
        >
          {state.message}
        </span>
      ) : null}
    </form>
  );
}
