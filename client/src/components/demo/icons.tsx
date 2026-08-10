import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const common = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.5,
  viewBox: "0 0 20 20",
};

export function OverviewIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M3.5 3.5h5v5h-5zM11.5 3.5h5v5h-5zM3.5 11.5h5v5h-5zM11.5 11.5h5v5h-5z" />
    </svg>
  );
}

export function DeploymentsIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M4 5.5 10 2l6 3.5-6 3.4zM4 9.2l6 3.4 6-3.4M4 12.9l6 3.4 6-3.4" />
    </svg>
  );
}

export function IncidentsIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M10 2.8 17 16H3zM10 7v4.2M10 14h.01" />
    </svg>
  );
}

export function PlaygroundIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="m7 5-4 5 4 5M13 5l4 5-4 5M11.5 3 8.5 17" />
    </svg>
  );
}

export function MonitorsIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M2.5 10h3l1.6-4 3.1 8 2.2-5 1.2 1H17.5" />
    </svg>
  );
}

export function ActivityIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M10 5.5V10l3 2M17 10a7 7 0 1 1-2.05-4.95" />
      <path d="M14.5 2.8v3h3" />
    </svg>
  );
}

export function IntegrationsIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M7.2 6.1 5.4 4.3a2.4 2.4 0 0 0-3.4 3.4l2.2 2.2a2.4 2.4 0 0 0 3.4 0l1-1" />
      <path d="m12.8 13.9 1.8 1.8a2.4 2.4 0 0 0 3.4-3.4l-2.2-2.2a2.4 2.4 0 0 0-3.4 0l-1 1M7.2 12.8l5.6-5.6" />
    </svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="m6.5 8 3.5 3.5L13.5 8" />
    </svg>
  );
}

export function ArrowUpRightIcon(props: IconProps) {
  return (
    <svg aria-hidden="true" {...common} {...props}>
      <path d="M5 15 15 5M7 5h8v8" />
    </svg>
  );
}
