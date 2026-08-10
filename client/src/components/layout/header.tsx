import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { navigation } from "@/content/landing";

export function Header() {
  return (
    <header className="relative z-20 bg-midnight">
      <div className="flex h-17 items-center border-b border-white/16 px-5 sm:px-8 lg:px-[6.25vw]">
        <Link
          className="block outline-none focus-visible:ring-2 focus-visible:ring-brand"
          href="/"
          aria-label="Histograph home"
        >
          <Logo priority />
        </Link>

        <nav aria-label="Primary navigation" className="ml-auto hidden md:block">
          <ul className="flex items-center gap-7">
            {navigation.map((item) => (
              <li key={item.label}>
                <Link
                  className="text-sm font-normal text-ink-muted transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
