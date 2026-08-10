import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { DemoNavigation } from "@/components/demo/navigation";

function EnvironmentControl({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-9 items-center border border-white/12 bg-white/[0.025] px-2.5 text-[13px] text-white sm:px-3 sm:text-sm">
      {children}
    </span>
  );
}

export function DemoShell({
  children,
  environment,
}: {
  children: React.ReactNode;
  environment: string;
}) {
  return (
    <div className="min-h-svh bg-midnight text-white">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-58 border-r border-white/10 bg-[#090909] md:flex md:flex-col">
        <div className="flex h-17 items-center border-b border-white/10 px-6">
          <Link
            aria-label="Histograph home"
            className="outline-none focus-visible:ring-2 focus-visible:ring-brand"
            href="/"
          >
            <Logo className="origin-left scale-[0.9]" priority />
          </Link>
        </div>

        <DemoNavigation />
      </aside>

      <div className="md:pl-58">
        <header className="sticky top-0 z-20 flex h-17 items-center border-b border-white/10 bg-midnight/95 px-5 backdrop-blur sm:px-7 lg:px-9">
          <Link
            aria-label="Histograph home"
            className="outline-none focus-visible:ring-2 focus-visible:ring-brand md:hidden"
            href="/"
          >
            <Logo className="origin-left scale-[0.72] sm:scale-[0.82]" priority />
          </Link>

          <div
            aria-label="Current workspace and environment"
            className="ml-auto flex items-center gap-2"
          >
            <EnvironmentControl>Demo</EnvironmentControl>
            <EnvironmentControl>{environment}</EnvironmentControl>
          </div>
        </header>

        <div className="border-b border-white/10 bg-midnight md:hidden">
          <DemoNavigation compact />
        </div>

        <main>{children}</main>
      </div>
    </div>
  );
}
