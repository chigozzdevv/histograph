import { ReleaseEvidence } from "@/components/landing/release-evidence";
import { landingSections } from "@/content/landing";

export function Monitoring() {
  return (
    <section className="border-b border-white/10 bg-[#0a0a0a]" id="workflow">
      <div className="grid lg:grid-cols-[0.95fr_1.05fr]">
        <div className="flex flex-col justify-center border-b border-white/8 px-5 py-20 sm:px-8 sm:py-24 lg:min-h-168 lg:border-r lg:border-b-0 lg:px-[6.25vw] lg:py-24">
          <h2 className="max-w-155 text-[clamp(2.25rem,3.55vw,4rem)] leading-[0.97] font-normal tracking-[-0.055em] text-white">
            {landingSections.monitoring.title}
          </h2>
          <p className="mt-6 max-w-125 text-base leading-7 tracking-[-0.02em] text-white/54 sm:text-lg">
            {landingSections.monitoring.description}
          </p>
        </div>
        <div className="flex items-center overflow-hidden px-5 py-14 sm:px-8 sm:py-18 lg:min-h-168 lg:px-[5vw] lg:py-24">
          <ReleaseEvidence />
        </div>
      </div>
    </section>
  );
}
