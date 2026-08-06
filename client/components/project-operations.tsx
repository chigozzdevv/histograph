"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type {
  Baseline,
  GitHubInstallation,
  ProtectedQuestion,
  RepositoryConnection,
  Run,
  Schedule,
  TestSuite,
} from "@/lib/types";

type ProjectOperationsProps = {
  projectId: string;
  organizationId: string;
  githubInstallUrl: string | null;
  githubInstallations: GitHubInstallation[];
  repositories: RepositoryConnection[];
  suites: TestSuite[];
  questions: ProtectedQuestion[];
  baselines: Baseline[];
  schedules: Schedule[];
  timezone: string;
};

function assetMappings(value: FormDataEntryValue | null) {
  return String(value ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [pattern, urnList] = line.split("=>", 2).map((item) => item.trim());
      if (!pattern || !urnList) {
        throw new Error("Each mapping must use: file pattern => DataHub URN");
      }
      return {
        pattern,
        asset_urns: urnList
          .split("|")
          .map((item) => item.trim())
          .filter(Boolean),
      };
    });
}

export function ProjectOperations({
  projectId,
  organizationId,
  githubInstallUrl,
  githubInstallations,
  repositories,
  suites,
  questions,
  baselines,
  schedules,
  timezone,
}: ProjectOperationsProps) {
  const router = useRouter();
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(
    key: string,
    operation: () => Promise<unknown>,
    event?: FormEvent<HTMLFormElement>,
  ) {
    event?.preventDefault();
    setActive(key);
    setError(null);
    try {
      await operation();
      event?.currentTarget.reset();
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The operation could not be completed",
      );
    } finally {
      setActive(null);
    }
  }

  async function connectInstallation(form: FormData) {
    await mutate(`/organizations/${organizationId}/github-installations`, {
      installation_id: Number(form.get("installation-id")),
    });
  }

  async function connectRepository(form: FormData) {
    await mutate(`/projects/${projectId}/repositories`, {
      github_installation_id: form.get("github-installation-id"),
      repository_id: Number(form.get("repository-id")),
      asset_mappings: assetMappings(form.get("asset-mappings")),
      run_all_when_unmapped: form.get("run-all-when-unmapped") === "on",
      protected_branches: String(form.get("protected-branches") ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      run_draft_pull_requests: form.get("run-drafts") === "on",
    });
  }

  async function createSchedule(form: FormData) {
    const [targetType, targetId] = String(form.get("target")).split(":", 2);
    await mutate<Schedule>(`/projects/${projectId}/schedules`, {
      name: form.get("name"),
      cron_expression: form.get("cron-expression"),
      timezone: form.get("timezone"),
      concurrency_policy: form.get("concurrency-policy"),
      suite_id: targetType === "suite" ? targetId : null,
      protected_question_id: targetType === "question" ? targetId : null,
    });
  }

  async function captureBaseline(questionId: string) {
    const run = await mutate<Run>(
      `/projects/${projectId}/protected-questions/${questionId}/baseline-runs`,
      {},
      { idempotencyKey: crypto.randomUUID() },
    );
    router.push(`/projects/${projectId}/runs/${run.id}`);
  }

  async function approveBaseline(
    questionId: string,
    baselineId: string,
    form: FormData,
  ) {
    await mutate(
      `/projects/${projectId}/protected-questions/${questionId}/baselines/${baselineId}/approve`,
      { justification: form.get("justification") },
    );
  }

  async function runAllQuestions() {
    const run = await mutate<Run>(
      `/projects/${projectId}/runs`,
      { trigger_type: "manual", selection: { all_active: true } },
      { idempotencyKey: crypto.randomUUID() },
    );
    router.push(`/projects/${projectId}/runs/${run.id}`);
  }

  return (
    <div className="operations-stack">
      <div className="checks-toolbar">
        <div>
          <h2>Protected questions</h2>
          <p>Questions Histograph checks whenever their context changes.</p>
        </div>
        <button
          className="primary-button"
          disabled={active === "run-all"}
          onClick={() => submit("run-all", runAllQuestions)}
          type="button"
        >
          {active === "run-all" ? "Starting…" : "Run checks"}
        </button>
      </div>
      <section className="question-list">
        {questions.map((question) => {
          const questionBaselines = baselines.filter(
            (baseline) => baseline.protected_question_id === question.id,
          );
          const draft = questionBaselines.find(
            (baseline) => baseline.status === "draft",
          );
          return (
            <article className="question-row" key={question.id}>
              <div>
                <h3>{question.name}</h3>
                <p>{question.criticality} importance</p>
              </div>
              <div className="question-actions">
                <span
                  className={
                    question.active_baseline_id
                      ? "baseline-ready"
                      : "baseline-missing"
                  }
                >
                  {question.active_baseline_id
                    ? "Baseline approved"
                    : draft
                      ? "Draft ready"
                      : "Needs baseline"}
                </span>
                {!draft && !question.active_baseline_id ? (
                  <button
                    disabled={active === `capture-${question.id}`}
                    onClick={() =>
                      submit(`capture-${question.id}`, () =>
                        captureBaseline(question.id),
                      )
                    }
                    type="button"
                  >
                    Capture baseline
                  </button>
                ) : null}
                {draft ? (
                  <form
                    className="approval-form"
                    onSubmit={(event) =>
                      submit(
                        `approve-${draft.id}`,
                        () =>
                          approveBaseline(
                            question.id,
                            draft.id,
                            new FormData(event.currentTarget),
                          ),
                        event,
                      )
                    }
                  >
                    <input
                      name="justification"
                      placeholder="Approval justification"
                      minLength={8}
                      required
                    />
                    <button disabled={active === `approve-${draft.id}`}>
                      Approve draft v{draft.version}
                    </button>
                  </form>
                ) : null}
              </div>
            </article>
          );
        })}
        {!questions.length ? (
          <div className="empty-state">
            Create a protected question to establish its baseline.
          </div>
        ) : null}
      </section>

      <details className="settings-panel">
        <summary>Automation</summary>
        <div className="operations-grid settings-content">
          {githubInstallUrl ||
          githubInstallations.length ||
          repositories.length ? (
            <article className="configuration-card">
              <div className="card-heading">
                <div>
                  <h3>GitHub</h3>
                  <p>Run checks when connected repositories change.</p>
                </div>
              </div>
              {githubInstallUrl ? (
                <a
                  className="secondary-link"
                  href={githubInstallUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  Install GitHub App ↗
                </a>
              ) : null}
              {githubInstallations.length ? (
                <form
                  onSubmit={(event) =>
                    submit(
                      "repository",
                      () =>
                        connectRepository(new FormData(event.currentTarget)),
                      event,
                    )
                  }
                >
                  <select
                    name="github-installation-id"
                    required
                    defaultValue=""
                  >
                    <option value="" disabled>
                      Select GitHub account
                    </option>
                    {githubInstallations.map((installation) => (
                      <option key={installation.id} value={installation.id}>
                        {installation.account_login}
                      </option>
                    ))}
                  </select>
                  <input
                    name="repository-id"
                    inputMode="numeric"
                    placeholder="Repository ID"
                    required
                  />
                  <details className="advanced-fields">
                    <summary>Change mapping</summary>
                    <input
                      name="protected-branches"
                      placeholder="Protected branches"
                    />
                    <textarea
                      name="asset-mappings"
                      rows={4}
                      placeholder="models/revenue/*.sql => DataHub URN"
                    />
                    <label className="checkbox-row">
                      <input
                        defaultChecked
                        name="run-all-when-unmapped"
                        type="checkbox"
                      />{" "}
                      Run every check when a change cannot be mapped
                    </label>
                    <label className="checkbox-row">
                      <input name="run-drafts" type="checkbox" /> Include draft
                      pull requests
                    </label>
                  </details>
                  <button disabled={active === "repository"}>
                    Connect repository
                  </button>
                </form>
              ) : githubInstallUrl ? (
                <details className="advanced-fields">
                  <summary>Connect an existing installation</summary>
                  <form
                    onSubmit={(event) =>
                      submit(
                        "github-installation",
                        () =>
                          connectInstallation(
                            new FormData(event.currentTarget),
                          ),
                        event,
                      )
                    }
                  >
                    <input
                      name="installation-id"
                      inputMode="numeric"
                      placeholder="Installation ID"
                      required
                    />
                    <button disabled={active === "github-installation"}>
                      Connect
                    </button>
                  </form>
                </details>
              ) : null}
              {repositories.map((repository) => (
                <p className="connected-resource" key={repository.id}>
                  {repository.full_name}
                  <strong>{repository.active ? "active" : "disabled"}</strong>
                </p>
              ))}
            </article>
          ) : null}

          <article className="configuration-card">
            <div className="card-heading">
              <div>
                <h3>Schedule</h3>
                <p>Run checks automatically.</p>
              </div>
            </div>
            <form
              onSubmit={(event) =>
                submit(
                  "schedule",
                  () => createSchedule(new FormData(event.currentTarget)),
                  event,
                )
              }
            >
              <input name="name" placeholder="Nightly checks" required />
              <select name="target" required defaultValue="">
                <option value="" disabled>
                  Choose checks
                </option>
                {suites.map((suite) => (
                  <option key={suite.id} value={`suite:${suite.id}`}>
                    {suite.name}
                  </option>
                ))}
                {questions.map((question) => (
                  <option key={question.id} value={`question:${question.id}`}>
                    {question.name}
                  </option>
                ))}
              </select>
              <input name="cron-expression" defaultValue="0 2 * * *" required />
              <input name="timezone" defaultValue={timezone} required />
              <select name="concurrency-policy" defaultValue="skip">
                <option value="skip">Skip if already running</option>
                <option value="queue">Run next</option>
                <option value="replace">Replace current run</option>
              </select>
              <button disabled={active === "schedule"}>Create schedule</button>
            </form>
            {schedules.map((schedule) => (
              <p className="connected-resource" key={schedule.id}>
                {schedule.name}
                <strong>{schedule.cron_expression}</strong>
              </p>
            ))}
          </article>
        </div>
      </details>

      {error ? <p className="form-error">{error}</p> : null}
    </div>
  );
}
