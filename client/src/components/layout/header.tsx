import Link from "next/link";

import { Mark } from "@/components/brand/mark";
import { navigation } from "@/content/landing";

export function Header() {
  return (
    <header className="relative z-20 border-b border-white/8">
      <div className="mx-auto flex h-18 max-w-360 items-center justify-between px-5 sm:px-8 lg:h-20 lg:px-12">
        <Link
          className="group flex items-center gap-2.5 rounded-sm text-white outline-none focus-visible:ring-2 focus-visible:ring-brand"
          href="/"
          aria-label="Histograph home"
        >
          <span className="grid size-8 place-items-center rounded-lg bg-brand text-midnight shadow-[0_0_28px_rgba(113,130,255,0.2)] transition-transform motion-safe:group-hover:-rotate-3">
            <Mark className="size-5" />
          </span>
          <span className="text-lg font-semibold tracking-[-0.035em]">Histograph</span>
        </Link>

        <nav aria-label="Primary navigation" className="hidden md:block">
          <ul className="flex items-center gap-8">
            {navigation.map((item) => (
              <li key={item.label}>
                <Link
                  className="rounded-sm text-sm font-medium text-ink-muted transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  href={item.href}
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
