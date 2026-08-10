"use client";

import Link from "next/link";
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { navigation } from "@/content/landing";

export function Header() {
  const [mobileOpen, setMobileOpen] = useState(false);

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

        <div className="relative ml-auto md:hidden">
          <button
            aria-controls="mobile-navigation"
            aria-expanded={mobileOpen}
            className="text-sm text-ink-muted outline-none transition-colors hover:text-white focus-visible:ring-2 focus-visible:ring-brand"
            onClick={() => setMobileOpen((open) => !open)}
            type="button"
          >
            Menu
          </button>
          {mobileOpen ? (
            <nav
              aria-label="Mobile navigation"
              className="absolute top-9 right-0 z-30 w-48 border border-white/14 bg-midnight"
              id="mobile-navigation"
            >
              <ul>
                {navigation.map((item) => (
                  <li className="border-b border-white/10 last:border-b-0" key={item.label}>
                    <Link
                      className="block px-5 py-4 text-sm text-ink-muted transition-colors hover:bg-white/[0.035] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
        </div>
      </div>
    </header>
  );
}
