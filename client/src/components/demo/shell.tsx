import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { DemoNavigation } from "@/components/demo/navigation";

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
            <span
              aria-current="page"
              className="inline-flex h-9 items-center border border-brand/70 bg-brand/15 px-2.5 text-[13px] text-brand-soft sm:px-3 sm:text-sm"
            >
              Demo
            </span>
            <details className="group relative">
              <summary className="inline-flex h-9 cursor-pointer list-none items-center border border-white/12 bg-white/[0.025] px-2.5 text-[13px] text-white outline-none transition-colors hover:border-white/24 focus-visible:border-brand/70 sm:px-3 sm:text-sm [&::-webkit-details-marker]:hidden">
                {environment}
              </summary>
              <div className="absolute top-full right-0 z-40 mt-2 w-36 border border-white/12 bg-[#111] px-3 py-2.5 text-center text-xs text-white/58 shadow-2xl">
                Coming soon
              </div>
            </details>
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
