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
