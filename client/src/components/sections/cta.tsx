import Link from "next/link";

import { landingSections } from "@/content/landing";

function Arrow() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 16 16">
      <path
        d="M3 8h9m0 0L8.5 4.5M12 8l-3.5 3.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function Cta() {
  return (
    <section className="landing-cta-grid relative overflow-hidden border-b border-white/10 bg-midnight px-5 py-24 sm:px-8 sm:py-32 lg:px-[6.25vw] lg:py-40">
      <div className="relative mx-auto flex min-h-96 max-w-255 flex-col items-center justify-center border border-white/12 bg-midnight/92 px-6 py-16 text-center sm:min-h-112 sm:px-12">
        <span aria-hidden="true" className="absolute top-0 left-1/2 h-20 w-px bg-gradient-to-b from-brand-soft/70 to-transparent" />
        <h2 className="max-w-190 text-[clamp(2.5rem,4vw,4.8rem)] leading-[0.95] font-normal tracking-[-0.055em] text-white">
          {landingSections.cta.title}
        </h2>
        <Link
          className="group mt-11 inline-flex min-h-17 items-center justify-center gap-6 border border-white bg-white px-6 text-base font-medium text-[#111] transition-colors hover:bg-brand hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-3 focus-visible:ring-offset-midnight"
          href={landingSections.cta.action.href}
        >
          {landingSections.cta.action.label}
          <span className="transition-transform motion-safe:group-hover:translate-x-1">
            <Arrow />
          </span>
        </Link>
      </div>
    </section>
  );
}
