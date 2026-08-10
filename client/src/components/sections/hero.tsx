import Link from "next/link";

import { RotatingTerms } from "@/components/hero/rotating-terms";
import { IncidentFlow } from "@/components/incident/flow";
import { heroContent } from "@/content/landing";

function ArrowUpRight() {
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

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-white/12 bg-midnight" id="product">
      <div className="grid min-h-[calc(100svh-4.25rem)] lg:grid-cols-2">
        <div className="relative z-10 flex flex-col justify-center px-5 py-18 sm:px-8 lg:py-24 lg:pr-[2vw] lg:pl-[6.25vw]">
          <h1 className="max-w-200 text-[clamp(2.25rem,11vw,4rem)] leading-[0.96] font-normal tracking-[-0.065em] text-white lg:text-[clamp(2.125rem,3.3vw,4.5rem)]">
            {heroContent.title.map((line) => (
              <span className="block lg:whitespace-nowrap" key={line}>
                {line}
              </span>
            ))}
            <span className="block lg:whitespace-nowrap">
              {heroContent.titleEnding.prefix}{" "}
              <RotatingTerms terms={heroContent.titleEnding.terms} />
            </span>
          </h1>
          <div className="mt-10">
            <Link
              className="group inline-flex min-h-17 items-center justify-center gap-6 border border-white bg-white px-6 text-base font-medium text-[#111] transition-colors hover:bg-brand hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-3 focus-visible:ring-offset-midnight"
              href={heroContent.action.href}
            >
              {heroContent.action.label}
              <span className="transition-transform motion-safe:group-hover:translate-x-1">
                <ArrowUpRight />
              </span>
            </Link>
          </div>
        </div>

        <div className="relative min-h-130 lg:min-h-0">
          <IncidentFlow />
        </div>
      </div>
    </section>
  );
}
