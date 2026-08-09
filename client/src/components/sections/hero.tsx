import Link from "next/link";

import { IncidentFlow } from "@/components/incident/flow";
import { heroContent } from "@/content/landing";

function ArrowUpRight() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 16 16">
      <path
        d="M4 12 12 4m0 0H6m6 0v6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden" id="product">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-20 bg-[radial-gradient(circle_at_78%_42%,rgba(113,130,255,0.09),transparent_31%),radial-gradient(circle_at_52%_110%,rgba(54,207,201,0.05),transparent_35%)]"
      />
      <div
        aria-hidden="true"
        className="hero-grid pointer-events-none absolute inset-0 -z-10 opacity-35 [mask-image:linear-gradient(to_bottom,black,transparent_88%)]"
      />

      <div className="mx-auto grid min-h-[calc(100svh-4.5rem)] max-w-360 items-center gap-14 px-5 py-16 sm:px-8 sm:py-20 lg:min-h-[calc(100svh-5rem)] lg:grid-cols-[0.9fr_1.1fr] lg:gap-12 lg:px-12 lg:py-24 xl:gap-20">
        <div className="max-w-170">
          <h1 className="max-w-165 text-[clamp(2.75rem,5vw,5.35rem)] leading-[0.97] font-medium tracking-[-0.065em] text-balance text-white xl:text-[5.35rem]">
            {heroContent.title}
          </h1>
          <p className="mt-7 max-w-145 text-base leading-7 text-pretty text-ink-muted sm:text-lg sm:leading-8">
            {heroContent.description}
          </p>
          <div className="mt-9">
            <Link
              className="group inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-brand px-5 text-sm font-semibold text-midnight shadow-[0_10px_35px_rgba(113,130,255,0.18)] transition-[background-color,transform,box-shadow] hover:-translate-y-0.5 hover:bg-brand-soft hover:shadow-[0_14px_42px_rgba(113,130,255,0.28)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-3 focus-visible:ring-offset-midnight active:translate-y-0 motion-reduce:transition-none"
              href={heroContent.action.href}
            >
              {heroContent.action.label}
              <span className="transition-transform motion-safe:group-hover:translate-x-0.5 motion-safe:group-hover:-translate-y-0.5">
                <ArrowUpRight />
              </span>
            </Link>
          </div>
        </div>

        <IncidentFlow />
      </div>
    </section>
  );
}
