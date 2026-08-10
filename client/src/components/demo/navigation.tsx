"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  ActivityIcon,
  DeploymentsIcon,
  IncidentsIcon,
  IntegrationsIcon,
  MonitorsIcon,
  OverviewIcon,
  PlaygroundIcon,
} from "@/components/demo/icons";
import { demoNavigation } from "@/content/demo";

const icons = {
  overview: OverviewIcon,
  deployments: DeploymentsIcon,
  playground: PlaygroundIcon,
  incidents: IncidentsIcon,
  monitors: MonitorsIcon,
  activity: ActivityIcon,
  integrations: IntegrationsIcon,
};

function isActive(pathname: string, href: string) {
  if (href === "/demo") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function DemoNavigation({ compact = false }: { compact?: boolean }) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Demo navigation"
      className={compact ? "overflow-x-auto px-4 py-2" : "px-3 py-6"}
    >
      <ul className={compact ? "flex min-w-max gap-1" : "space-y-1"}>
        {demoNavigation.map((item) => {
          const Icon = icons[item.icon];
          const active = isActive(pathname, item.href);

          return (
            <li key={item.label}>
              <Link
                aria-current={active ? "page" : undefined}
                className={`flex h-10 items-center gap-3 px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                  active
                    ? "bg-white/[0.065] text-white"
                    : "text-white/46 hover:bg-white/[0.035] hover:text-white/78"
                }`}
                href={item.href}
              >
                <Icon className="size-4.5" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
