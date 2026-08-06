"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type { AgentTarget, DataHubConnection, TestSuite } from "@/lib/types";

type ProjectConfigurationProps = {
  projectId: string;
  datahubConnections: DataHubConnection[];
  agentTargets: AgentTarget[];
  suites: TestSuite[];
  hasQuestions: boolean;
};

function commaSeparated(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function slugify(value: FormDataEntryValue | null) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function ProjectConfiguration({
  projectId,
  datahubConnections,
  agentTargets,
  suites,
  hasQuestions,
}: ProjectConfigurationProps) {
  const router = useRouter();
  const [activeForm, setActiveForm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const datahub = datahubConnections.find((item) => item.status === "ready");
  const agent = agentTargets.find((item) => item.status === "ready");
  const currentStep = !datahub
    ? "datahub"
    : !agent
      ? "agent"
      : !suites.length
        ? "suite"
        : "question";

  async function submit(
    key: string,
    operation: () => Promise<unknown>,
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setActiveForm(key);
    setError(null);
    try {
      await operation();
      event.currentTarget.reset();
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The connection could not be saved",
      );
    } finally {
      setActiveForm(null);
    }
  }

  async function createDataHubConnection(form: FormData) {
    const baseUrl = String(form.get("base-url") ?? "").replace(/\/$/, "");
    const customMcpUrl = String(form.get("mcp-url") ?? "").trim();
    const connection = await mutate<DataHubConnection>(
      `/projects/${projectId}/datahub-connections`,
      {
        name: "DataHub",
        mode: form.get("mode"),
        endpoint_url: baseUrl,
        mcp_url: customMcpUrl || `${baseUrl}/integrations/ai/mcp`,
        secret_location: "managed",
        token: form.get("token"),
      },
    );
    await mutate(
      `/projects/${projectId}/datahub-connections/${connection.id}/test`,
      {},
    );
  }

  async function createAgentTarget(form: FormData) {
    const target = await mutate<AgentTarget>(
      `/projects/${projectId}/agent-targets`,
      {
        name: form.get("name"),
        adapter_type: "datahub_analytics_agent",
        base_url: form.get("base-url"),
        engine_name:
          String(form.get("engine-name") ?? "").trim() || "warehouse",
        secret_location: "managed",
        token: String(form.get("token") ?? "") || null,
      },
    );
    await mutate(`/projects/${projectId}/agent-targets/${target.id}/test`, {});
  }

  async function createSuite(form: FormData) {
    const name = form.get("name");
    await mutate<TestSuite>(`/projects/${projectId}/test-suites`, {
      name,
      slug: slugify(name),
      description: null,
    });
  }

  async function createQuestion(form: FormData) {
    const name = form.get("name");
    await mutate(
      `/projects/${projectId}/test-suites/${form.get("suite-id")}/protected-questions`,
      {
        stable_key: slugify(name),
        name,
        description: null,
        criticality: form.get("criticality"),
        agent_target_id: form.get("agent-target-id"),
        question: form.get("question"),
        context_query: String(form.get("context-query") ?? "") || null,
        assets: { required: commaSeparated(form.get("required-assets")) },
        sql: {
          required_tables: commaSeparated(form.get("required-tables")),
          required_columns: commaSeparated(form.get("required-columns")),
          require_query: true,
        },
        result: {
          required_columns: commaSeparated(form.get("result-columns")),
        },
        response: {
          required_phrases: commaSeparated(form.get("required-phrases")),
        },
      },
    );
  }

  if (hasQuestions) {
    return (
      <details className="settings-panel">
        <summary>Connections</summary>
        <div className="connection-list">
          <div className="connection-confirmed">
            <span>✓</span>
            <div>
              <strong>{datahub?.name ?? "DataHub"}</strong>
              <small>Context connected</small>
            </div>
          </div>
          <div className="connection-confirmed">
            <span>✓</span>
            <div>
              <strong>{agent?.name ?? "Analytics agent"}</strong>
              <small>Agent connected</small>
            </div>
          </div>
        </div>
      </details>
    );
  }

  return (
    <div className="setup-shell">
      <ol className="setup-progress" aria-label="Project setup progress">
        <li
          className={
            datahub ? "complete" : currentStep === "datahub" ? "current" : ""
          }
        >
          <span>1</span>DataHub
        </li>
        <li
          className={
            agent ? "complete" : currentStep === "agent" ? "current" : ""
          }
        >
          <span>2</span>Agent
        </li>
        <li
          className={
            currentStep === "suite" || currentStep === "question"
              ? "current"
              : ""
          }
        >
          <span>3</span>First check
        </li>
      </ol>

      {currentStep === "datahub" ? (
        <form
          className="setup-card"
          onSubmit={(event) =>
            submit(
              "datahub",
              () => createDataHubConnection(new FormData(event.currentTarget)),
              event,
            )
          }
        >
          <div className="form-heading">
            <span>1</span>
            <div>
              <h2>Connect DataHub</h2>
              <p>
                Histograph uses your catalog to understand what each answer
                depends on.
              </p>
            </div>
          </div>
          <label>
            DataHub URL
            <input
              name="base-url"
              placeholder="https://company.acryl.io"
              type="url"
              required
            />
          </label>
          <label>
            Access token
            <input name="token" type="password" required />
          </label>
          <details className="advanced-fields">
            <summary>Advanced connection options</summary>
            <label>
              Deployment
              <select name="mode" defaultValue="cloud">
                <option value="cloud">DataHub Cloud</option>
                <option value="self_hosted">Self-hosted</option>
              </select>
            </label>
            <label>
              Custom MCP URL
              <input name="mcp-url" placeholder="Optional" type="url" />
            </label>
          </details>
          <button disabled={activeForm === "datahub"}>
            {activeForm === "datahub"
              ? "Checking connection…"
              : "Connect DataHub"}
          </button>
        </form>
      ) : null}

      {currentStep === "agent" ? (
        <form
          className="setup-card"
          onSubmit={(event) =>
            submit(
              "agent",
              () => createAgentTarget(new FormData(event.currentTarget)),
              event,
            )
          }
        >
          <div className="form-heading">
            <span>2</span>
            <div>
              <h2>Connect your analytics agent</h2>
              <p>
                Histograph will ask this agent your protected questions and
                check its answers.
              </p>
            </div>
          </div>
          <div className="connection-confirmed">
            <span>✓</span>
            <div>
              <strong>DataHub</strong>
              <small>DataHub connected</small>
            </div>
          </div>
          <label>
            Agent name
            <input name="name" placeholder="Revenue agent" required />
          </label>
          <label>
            Agent URL
            <input
              name="base-url"
              placeholder="https://agent.company.com"
              type="url"
              required
            />
          </label>
          <label>
            API token <small>Optional</small>
            <input name="token" type="password" />
          </label>
          <details className="advanced-fields">
            <summary>Advanced connection options</summary>
            <label>
              Query engine
              <input defaultValue="warehouse" name="engine-name" />
            </label>
          </details>
          <button disabled={activeForm === "agent"}>
            {activeForm === "agent" ? "Checking connection…" : "Connect agent"}
          </button>
        </form>
      ) : null}

      {currentStep === "suite" ? (
        <form
          className="setup-card"
          onSubmit={(event) =>
            submit(
              "suite",
              () => createSuite(new FormData(event.currentTarget)),
              event,
            )
          }
        >
          <div className="form-heading">
            <span>3</span>
            <div>
              <h2>Name your first check group</h2>
              <p>
                Group related questions, such as revenue, growth, or executive
                reporting.
              </p>
            </div>
          </div>
          <label>
            Group name
            <input name="name" placeholder="Executive metrics" required />
          </label>
          <button disabled={activeForm === "suite"}>
            {activeForm === "suite" ? "Creating…" : "Continue"}
          </button>
        </form>
      ) : null}

      {currentStep === "question" ? (
        <form
          className="setup-card question-setup"
          onSubmit={(event) =>
            submit(
              "question",
              () => createQuestion(new FormData(event.currentTarget)),
              event,
            )
          }
        >
          <div className="form-heading">
            <span>3</span>
            <div>
              <h2>Add the first question</h2>
              <p>
                Choose an important question whose answer should stay reliable.
              </p>
            </div>
          </div>
          <input name="suite-id" type="hidden" value={suites[0]?.id} />
          <input name="agent-target-id" type="hidden" value={agent?.id} />
          <label>
            Check name
            <input name="name" placeholder="Net revenue by country" required />
          </label>
          <label>
            Question
            <textarea
              name="question"
              rows={3}
              placeholder="What was net revenue by country last month?"
              required
            />
          </label>
          <label>
            Importance
            <select name="criticality" defaultValue="high">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <details className="advanced-fields">
            <summary>Answer rules</summary>
            <p>Optional rules make the check more precise.</p>
            <label>
              DataHub search
              <input name="context-query" />
            </label>
            <label>
              Required assets
              <input
                name="required-assets"
                placeholder="DataHub URNs, comma-separated"
              />
            </label>
            <label>
              Required SQL tables
              <input name="required-tables" placeholder="finance.net_revenue" />
            </label>
            <label>
              Required SQL columns
              <input
                name="required-columns"
                placeholder="country, net_revenue"
              />
            </label>
            <label>
              Required result columns
              <input name="result-columns" placeholder="country, net_revenue" />
            </label>
            <label>
              Required answer phrases
              <input name="required-phrases" placeholder="net revenue" />
            </label>
          </details>
          <button disabled={activeForm === "question"}>
            {activeForm === "question" ? "Creating check…" : "Create check"}
          </button>
        </form>
      ) : null}

      {error ? <p className="form-error">{error}</p> : null}
    </div>
  );
}
