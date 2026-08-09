export const navigation = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#workflow" },
  { label: "Docs", href: "#docs" },
] as const;

export const heroContent = {
  title: "From model failure to root cause.",
  description: "Trace production failures through DataHub lineage and verify recovery.",
  action: {
    label: "Run a demo",
    href: "#demo",
  },
} as const;
