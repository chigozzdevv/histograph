"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type { AgentTarget, DataHubConnection, Run, Schedule, TestSuite } from "@/lib/types";

type ProjectConfigurationProps = {
  projectId: string;
  datahubConnections: DataHubConnection[];
  agentTargets: AgentTarget[];
  suites: TestSuite[];
};

function commaSeparated(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProjectConfiguration({
  projectId,
  datahubConnections,
  agentTargets,
  suites,
}: ProjectConfigurationProps) {
  const router = useRouter();
  const [activeForm, setActiveForm] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setError(cause instanceof Error ? cause.message : "The configuration could not be saved");
    } finally {
      setActiveForm(null);
    }
  }

  async function createDataHubConnection(form: FormData) {
    const connection = await mutate<DataHubConnection>(
      `/projects/${projectId}/datahub-connections`,
      {
        name: form.get("name"),
        mode: form.get("mode"),
        endpoint_url: form.get("endpoint-url"),
        mcp_url: form.get("mcp-url"),
        secret_location: "managed",
        token: form.get("token"),
      },
    );
    await mutate(`/projects/${projectId}/datahub-connections/${connection.id}/test`, {});
  }

  async function createAgentTarget(form: FormData) {
    const target = await mutate<AgentTarget>(`/projects/${projectId}/agent-targets`, {
      name: form.get("name"),
      adapter_type: "datahub_analytics_agent",
      base_url: form.get("base-url"),
      engine_name: form.get("engine-name"),
      secret_location: "managed",
      token: String(form.get("token") ?? "") || null,
    });
    await mutate(`/projects/${projectId}/agent-targets/${target.id}/test`, {});
  }

  async function createQuestion(form: FormData) {
    await mutate(`/projects/${projectId}/test-suites/${form.get("suite-id")}/protected-questions`, {
      stable_key: form.get("stable-key"),
      name: form.get("name"),
      description: String(form.get("description") ?? "") || null,
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
      result: { required_columns: commaSeparated(form.get("result-columns")) },
      response: { required_phrases: commaSeparated(form.get("required-phrases")) },
    });
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
    <div className="configuration-grid">
      <article className="configuration-card">
        <div className="card-heading">
          <span className={datahubConnections.some((item) => item.status === "ready") ? "ready-dot" : "empty-dot"} />
          <div>
            <h3>DataHub context</h3>
            <p>Metadata, schemas, lineage, ownership and definitions.</p>
          </div>
        </div>
        {datahubConnections[0] ? (
          <p className="connected-resource">
            {datahubConnections[0].name} <strong>{datahubConnections[0].status}</strong>
          </p>
        ) : null}
        <form onSubmit={(event) => submit("datahub", () => createDataHubConnection(new FormData(event.currentTarget)), event)}>
          <input name="name" placeholder="Production DataHub" required />
          <select name="mode" defaultValue="cloud"><option value="cloud">DataHub Cloud</option><option value="self_hosted">Self-hosted</option></select>
          <input name="endpoint-url" type="url" placeholder="https://tenant.acryl.io" required />
          <input name="mcp-url" type="url" placeholder="https://tenant.acryl.io/integrations/ai/mcp" required />
          <input name="token" type="password" placeholder="Service-account token" required />
          <button disabled={activeForm === "datahub"}>Save and verify</button>
        </form>
      </article>

      <article className="configuration-card">
        <div className="card-heading">
          <span className={agentTargets.some((item) => item.status === "ready") ? "ready-dot" : "empty-dot"} />
          <div><h3>Analytics agent</h3><p>The system whose answers Histograph protects.</p></div>
        </div>
        {agentTargets[0] ? <p className="connected-resource">{agentTargets[0].name} <strong>{agentTargets[0].status}</strong></p> : null}
        <form onSubmit={(event) => submit("agent", () => createAgentTarget(new FormData(event.currentTarget)), event)}>
          <input name="name" placeholder="Revenue agent" required />
          <input name="base-url" type="url" placeholder="https://agent.internal" required />
          <input name="engine-name" placeholder="warehouse" required />
          <input name="token" type="password" placeholder="Agent API token, if required" />
          <button disabled={activeForm === "agent"}>Save and verify</button>
        </form>
      </article>

      <article className="configuration-card">
        <div className="card-heading">
          <span className={suites.length ? "ready-dot" : "empty-dot"} />
          <div><h3>Protected suite</h3><p>Versioned business questions and assertions.</p></div>
        </div>
        <form onSubmit={(event) => submit("suite", () => mutate<TestSuite>(`/projects/${projectId}/test-suites`, { name: new FormData(event.currentTarget).get("name"), slug: new FormData(event.currentTarget).get("slug"), description: new FormData(event.currentTarget).get("description") || null }), event)}>
          <input name="name" placeholder="Executive metrics" required />
          <input name="slug" placeholder="executive-metrics" required />
          <input name="description" placeholder="Questions used in weekly reporting" />
          <button disabled={activeForm === "suite"}>Create suite</button>
        </form>
      </article>

      <article className="configuration-card wide-card">
        <div className="card-heading">
          <span className={suites.length && agentTargets.length ? "ready-dot" : "empty-dot"} />
          <div><h3>Add a protected question</h3><p>Define what correct agent behavior means before context changes.</p></div>
        </div>
        <form className="question-form" onSubmit={(event) => submit("question", () => createQuestion(new FormData(event.currentTarget)), event)}>
          <select name="suite-id" required defaultValue=""><option value="" disabled>Select suite</option>{suites.map((suite) => <option value={suite.id} key={suite.id}>{suite.name}</option>)}</select>
          <select name="agent-target-id" required defaultValue=""><option value="" disabled>Select agent</option>{agentTargets.filter((target) => target.active).map((target) => <option value={target.id} key={target.id}>{target.name}</option>)}</select>
          <input name="stable-key" placeholder="net-revenue-by-country" required />
          <input name="name" placeholder="Net revenue by country" required />
          <select name="criticality" defaultValue="high"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select>
          <input name="description" placeholder="Why this business question matters" />
          <textarea className="form-span" name="question" rows={3} placeholder="What was net revenue by country last month?" required />
          <input name="context-query" placeholder="DataHub context search" />
          <input name="required-assets" placeholder="Required DataHub URNs, comma-separated" />
          <input name="required-tables" placeholder="Required SQL tables" />
          <input name="required-columns" placeholder="Required SQL columns" />
          <input name="result-columns" placeholder="Required result columns" />
          <input name="required-phrases" placeholder="Required answer phrases" />
          <button disabled={!suites.length || !agentTargets.length || activeForm === "question"}>Create protected question</button>
        </form>
      </article>

      {error ? <p className="form-error configuration-error">{error}</p> : null}
      <button className="primary-button run-button" onClick={runAllQuestions} type="button">
        Run all protected questions
      </button>
    </div>
  );
}
