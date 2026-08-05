import type { Run } from "@/lib/types";

type StatusBadgeProps = {
  status: Run["status"];
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-${status}`}>{status.replace("_", " ")}</span>;
}
