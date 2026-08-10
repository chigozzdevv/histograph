import { Workspace } from "@/components/product/workspace";
import { ecosystem, landingSections } from "@/content/landing";

export function Product() {
  return (
    <section className="border-b border-white/10 bg-midnight" id="product">
      <div className="border-b border-white/10 px-5 sm:px-8 lg:px-[6.25vw]">
        <div className="grid grid-cols-3 border-x border-white/10">
          {ecosystem.map((item, index) => (
            <div
              className={`flex min-h-18 min-w-0 items-center px-3 py-4 sm:min-h-28 sm:justify-between sm:gap-5 sm:px-6 sm:py-5 ${
                index > 0 ? "border-l border-white/10" : ""
              }`}
              key={item.name}
            >
              <span className="text-sm leading-4 tracking-[-0.02em] text-white/82 sm:text-base sm:leading-5">
                {item.name}
              </span>
              <span className="hidden max-w-32 text-right font-mono text-[9px] leading-4 tracking-[0.1em] text-white/30 uppercase sm:block">
                {item.detail}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="px-5 py-20 sm:px-8 sm:py-26 lg:px-[6.25vw] lg:py-32">
        <div className="mx-auto max-w-400">
          <div className="max-w-270">
            <h2 className="text-[clamp(2.5rem,4vw,5rem)] leading-[0.95] font-normal tracking-[-0.06em] text-white">
              {landingSections.product.title}
            </h2>
            <p className="mt-6 max-w-180 text-base leading-7 tracking-[-0.02em] text-white/56 sm:text-lg sm:leading-7">
              {landingSections.product.description}
            </p>
          </div>

          <div className="mt-12 sm:mt-16">
            <Workspace />
          </div>
        </div>
      </div>
    </section>
  );
}
