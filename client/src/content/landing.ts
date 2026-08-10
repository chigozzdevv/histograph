export const navigation = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#workflow" },
  { label: "Docs", href: "#docs" },
] as const;

export const heroContent = {
  title: [
    "Lineage-aware observability &",
    "root-cause tracing for incident",
  ],
  titleEnding: {
    prefix: "response in",
    terms: ["production ML", "feature pipelines", "model serving"],
  },
  action: {
    label: "Run a demo",
    href: "/demo",
  },
} as const;

export const ecosystem = [
  { name: "DataHub", detail: "Lineage context" },
  { name: "GitHub", detail: "Desired state + approval" },
  { name: "Model runtime", detail: "Telemetry + observed state" },
] as const;

export const landingSections = {
  product: {
    title: "Production ML incidents, fully connected.",
    description:
      "Model health, lineage evidence, deployment state, and recovery in one workspace.",
  },
  monitoring: {
    title: "Compare releases on production evidence.",
    description:
      "Stable and candidate versions share the same labeled window and an explicit performance boundary.",
  },
  investigation: {
    title: "See which change reached production.",
    description:
      "Histograph correlates monitor evidence with DataHub lineage and records the exact path on the incident.",
  },
  response: {
    title: "Approval stays in your workflow.",
    description:
      "Merge a rollback PR or authorize your remediation adapter. Histograph records who approved what.",
  },
  recovery: {
    title: "Recovery requires fresh production evidence.",
    description:
      "Execution, observed runtime state, and a new healthy monitor window must agree before the incident resolves.",
  },
  integrations: {
    title: "Connect without replacing your stack.",
    description:
      "DataHub for lineage. GitHub for desired state and approvals. Your runtime for telemetry and recovery evidence.",
  },
  cta: {
    title: "Explore the full incident workflow.",
    action: {
      label: "Run a demo",
      href: "/demo",
    },
  },
} as const;

export const footerNavigation = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#workflow" },
  { label: "Docs", href: "#docs" },
  { label: "Demo", href: "/demo" },
] as const;
