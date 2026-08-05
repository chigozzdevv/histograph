"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { createRun } from "@/lib/api-client";
import type { RunRequest } from "@/lib/types";

function values(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function RunForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const id = String(form.get("test-id"));
    const request: RunRequest = {
      test_case: {
        id,
        name: String(form.get("test-name")),
        question: String(form.get("question")),
        context_query: String(form.get("context-query") || "") || undefined,
        assets: {
          required: values(form.get("required-assets")),
          forbidden: values(form.get("forbidden-assets")),
        },
        sql: {
          dialect: String(form.get("sql-dialect") || "") || undefined,
          required_tables: values(form.get("required-tables")),
          forbidden_tables: values(form.get("forbidden-tables")),
          required_columns: values(form.get("required-sql-columns")),
          forbidden_columns: values(form.get("forbidden-sql-columns")),
          require_query: true,
        },
        result: {
          required_columns: values(form.get("required-result-columns")),
          min_rows: Number(form.get("minimum-rows") || 0),
        },
        response: {
          required_phrases: values(form.get("required-phrases")),
          forbidden_phrases: values(form.get("forbidden-phrases")),
        },
      },
      datahub: {
        mcp_url: String(form.get("datahub-url")),
        token: String(form.get("datahub-token")),
      },
      agent: {
        base_url: String(form.get("agent-url")),
        engine_name: String(form.get("engine-name")),
        token: String(form.get("agent-token") || "") || undefined,
      },
    };
    try {
      const run = await createRun(request);
      router.push(`/runs/${run.id}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The run could not be started");
      setSubmitting(false);
    }
  }

  return (
    <form className="run-form" onSubmit={submit}>
      <div className="form-section">
        <div className="section-heading">
          <span>01</span>
          <div>
            <h3>Agent test</h3>
            <p>Define the question and its deterministic expectations.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Test ID
            <input name="test-id" defaultValue="net-revenue" pattern="[a-z0-9][a-z0-9-]*" required />
          </label>
          <label>
            Test name
            <input name="test-name" defaultValue="Net revenue by country" required />
          </label>
          <label className="form-span">
            Business question
            <textarea
              name="question"
              defaultValue="What was our net revenue by country last month?"
              rows={3}
              required
            />
          </label>
          <label className="form-span">
            DataHub search query
            <input name="context-query" defaultValue="net revenue" />
          </label>
          <label>
            Required tables
            <input name="required-tables" placeholder="finance.net_revenue, refunds" />
          </label>
          <label>
            Required SQL columns
            <input name="required-sql-columns" placeholder="country, net_revenue" />
          </label>
          <label>
            Required result columns
            <input name="required-result-columns" placeholder="country, net_revenue" />
          </label>
          <label>
            Required response phrases
            <input name="required-phrases" placeholder="net revenue, USD" />
          </label>
          <label>
            Required DataHub URNs
            <input name="required-assets" placeholder="urn:li:dataset:(...)" />
          </label>
          <label>
            Forbidden DataHub URNs
            <input name="forbidden-assets" placeholder="urn:li:dataset:(...)" />
          </label>
          <label>
            Forbidden tables
            <input name="forbidden-tables" placeholder="legacy.revenue" />
          </label>
          <label>
            Forbidden SQL columns
            <input name="forbidden-sql-columns" placeholder="gross_revenue" />
          </label>
          <label>
            Forbidden response phrases
            <input name="forbidden-phrases" placeholder="approximately" />
          </label>
          <label>
            SQL dialect
            <input name="sql-dialect" placeholder="postgres" />
          </label>
          <label>
            Minimum result rows
            <input name="minimum-rows" type="number" min="0" defaultValue="1" />
          </label>
        </div>
      </div>

      <div className="form-section">
        <div className="section-heading">
          <span>02</span>
          <div>
            <h3>Connections</h3>
            <p>Credentials are used for this execution and are never stored in run evidence.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            DataHub MCP URL
            <input name="datahub-url" type="url" placeholder="https://tenant.acryl.io/integrations/ai/mcp" required />
          </label>
          <label>
            DataHub service token
            <input name="datahub-token" type="password" required />
          </label>
          <label>
            Analytics Agent URL
            <input name="agent-url" type="url" placeholder="http://localhost:8100" required />
          </label>
          <label>
            Warehouse engine name
            <input name="engine-name" placeholder="warehouse" required />
          </label>
          <label>
            Analytics Agent token
            <input name="agent-token" type="password" />
          </label>
        </div>
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      <button className="primary-button" type="submit" disabled={submitting}>
        {submitting ? "Running verification…" : "Run verification"}
      </button>
    </form>
  );
}
