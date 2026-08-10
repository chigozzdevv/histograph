import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { footerNavigation } from "@/content/landing";

export function Footer() {
  return (
    <footer className="dashboard-register bg-midnight px-5 py-10 sm:px-8 lg:px-[6.25vw] lg:py-12">
      <div className="mx-auto flex max-w-400 flex-col gap-10 border-x border-white/10 px-5 py-6 sm:px-7 lg:flex-row lg:items-end lg:justify-between lg:px-9">
        <div>
          <Link
            aria-label="Histograph home"
            className="inline-block outline-none focus-visible:ring-2 focus-visible:ring-brand"
            href="/"
          >
            <Logo />
          </Link>
          <p className="mt-5 max-w-80 font-mono text-[10px] leading-5 tracking-[0.08em] text-white/38 uppercase">
            Production ML incident response
          </p>
        </div>

        <div className="flex flex-col gap-8 sm:flex-row sm:items-end sm:gap-14">
          <nav aria-label="Footer navigation">
            <ul className="grid grid-cols-2 gap-x-8 gap-y-3 sm:flex sm:gap-7">
              {footerNavigation.map((item) => (
                <li key={item.label}>
                  <Link
                    className="text-sm text-white/56 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    href={item.href}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <p className="font-mono text-[9px] tracking-[0.1em] text-white/34 uppercase">
            © {new Date().getFullYear()} Histograph
          </p>
        </div>
      </div>
    </footer>
  );
}
