import { LineageEvidence } from "@/components/landing/lineage-evidence";
import { landingSections } from "@/content/landing";

export function Investigation() {
  return (
    <section className="border-b border-white/10 bg-midnight">
      <div className="px-5 py-20 sm:px-8 sm:py-24 lg:px-[6.25vw] lg:py-32">
        <div className="mx-auto max-w-400">
          <div className="max-w-220">
            <h2 className="text-[clamp(2.25rem,3.55vw,4rem)] leading-[0.97] font-normal tracking-[-0.055em] text-white">
              {landingSections.investigation.title}
            </h2>
            <p className="mt-6 max-w-135 text-base leading-7 tracking-[-0.02em] text-white/54 sm:text-lg">
              {landingSections.investigation.description}
            </p>
          </div>
          <div className="mt-12 sm:mt-16">
            <LineageEvidence />
          </div>
        </div>
      </div>
    </section>
  );
}
