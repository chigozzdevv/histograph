import { ConnectorRegister } from "@/components/landing/connector-register";
import { landingSections } from "@/content/landing";

export function Integrations() {
  return (
    <section className="border-b border-white/10 bg-[#0a0a0a]" id="docs">
      <div className="px-5 py-20 sm:px-8 sm:py-24 lg:px-[6.25vw] lg:py-32">
        <div className="mx-auto grid max-w-400 gap-12 sm:gap-16 lg:grid-cols-[0.85fr_1.15fr] lg:items-start lg:gap-22">
          <div>
            <h2 className="max-w-180 text-[clamp(2.25rem,3.55vw,4rem)] leading-[0.97] font-normal tracking-[-0.055em] text-white">
              {landingSections.integrations.title}
            </h2>
            <p className="mt-6 max-w-135 text-base leading-7 tracking-[-0.02em] text-white/54 sm:text-lg">
              {landingSections.integrations.description}
            </p>
          </div>
          <ConnectorRegister />
        </div>
      </div>
    </section>
  );
}
