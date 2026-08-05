export type Finding = {
  code: string;
  message: string;
  passed: boolean;
  level: "info" | "warning" | "error";
  evidence: Record<string, unknown>;
};

export type SqlExecution = {
  sql: string;
  columns: string[];
  rows: unknown[];
  truncated: boolean;
};

export type RunResult = {
  run_id: string;
  status: "passed" | "failed" | "error";
  started_at: string;
  completed_at: string;
  evidence: {
    context: {
      query: string;
      asset_urns: string[];
      entities: Record<string, unknown>[];
    };
    selected_asset_urns: string[];
    sql_executions: SqlExecution[];
    final_response: string;
    errors: string[];
  };
  evaluation: {
    status: "passed" | "failed" | "error";
    findings: Finding[];
  };
};

export type Run = {
  id: string;
  test_case_id: string;
  test_case_name: string;
  status: "executing" | "passed" | "failed" | "error";
  started_at: string;
  completed_at: string | null;
  error: string | null;
  result: RunResult | null;
};

export type RunRequest = {
  test_case: {
    id: string;
    name: string;
    question: string;
    context_query?: string;
    assets: {
      required: string[];
      forbidden: string[];
    };
    sql: {
      dialect?: string;
      required_tables: string[];
      forbidden_tables: string[];
      required_columns: string[];
      forbidden_columns: string[];
      require_query: boolean;
    };
    result: {
      required_columns: string[];
      min_rows?: number;
    };
    response: {
      required_phrases: string[];
      forbidden_phrases: string[];
    };
  };
  datahub: {
    mcp_url: string;
    token: string;
  };
  agent: {
    base_url: string;
    engine_name: string;
    token?: string;
  };
};
