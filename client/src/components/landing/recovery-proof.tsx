function ProofCell({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "success" }) {
  return (
    <div className="min-w-0 px-4 py-4 sm:px-5 sm:py-5">
      <p className="font-mono text-[9px] tracking-[0.1em] text-white/28 uppercase">{label}</p>
      <div className="mt-2 flex items-center gap-2">
        {tone === "success" ? <span aria-hidden="true" className="size-1.5 shrink-0 bg-success" /> : null}
        <p className={tone === "success" ? "truncate font-mono text-[10px] text-success" : "truncate font-mono text-[10px] text-white/58"}>
          {value}
        </p>
      </div>
    </div>
  );
}

export function RecoveryProof() {
  return (
    <figure className="overflow-hidden border border-white/10 bg-[#090909]">
      <div className="flex min-h-14 items-center justify-between gap-5 border-b border-white/8 px-4 sm:px-6">
        <div>
          <p className="text-sm text-white/72">Recovery verification</p>
          <p className="mt-0.5 font-mono text-[9px] tracking-[0.08em] text-white/28 uppercase">
            Post-remediation evidence
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-success uppercase">
          <span aria-hidden="true" className="size-1.5 bg-success" />
          Resolved
        </div>
      </div>

      <div className="px-4 pt-6 sm:px-6 sm:pt-8">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[9px] tracking-[0.08em] uppercase">
          <span className="inline-flex items-center gap-2 text-white/38">
            <span aria-hidden="true" className="h-px w-5 bg-brand-soft" />
            Feature scale
          </span>
          <span className="inline-flex items-center gap-2 text-white/38">
            <span aria-hidden="true" className="h-px w-5 bg-success" />
            Production recall
          </span>
          <span className="inline-flex items-center gap-2 text-white/30">
            <span aria-hidden="true" className="w-5 border-t border-dashed border-white/30" />
            Healthy boundary
          </span>
        </div>

        <div className="mt-5 border border-white/8 sm:hidden">
          <div className="border-b border-white/8 px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <span className="font-mono text-[9px] tracking-[0.08em] text-brand-soft uppercase">
                Rollback observed
              </span>
              <span className="font-mono text-[9px] text-white/34">14:18</span>
            </div>
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-x-5 gap-y-3 px-4 py-4 font-mono text-[10px]">
            <span className="text-white/34">Feature scale</span>
            <span className="text-brand-soft">×100 → ×1</span>
            <span className="text-white/34">Production recall</span>
            <span className="text-success">0.0% → 14.3%</span>
            <span className="text-white/34">Healthy boundary</span>
            <span className="text-white/58">9.3%</span>
          </div>
          <div className="border-t border-white/8 px-4 py-3">
            <div className="h-1.5 bg-white/6">
              <span className="block h-full w-full bg-success/72" />
            </div>
            <p className="mt-2 font-mono text-[9px] text-success">240 fresh labeled outcomes</p>
          </div>
        </div>

        <svg
          aria-hidden="true"
          className="mt-5 hidden h-auto w-full sm:block"
          preserveAspectRatio="none"
          viewBox="0 0 820 310"
        >
          <defs>
            <linearGradient id="recovery-proof-window" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#77d9a7" stopOpacity="0.02" />
              <stop offset="1" stopColor="#77d9a7" stopOpacity="0.12" />
            </linearGradient>
          </defs>

          <g fill="none" stroke="rgba(255,255,255,0.055)" strokeWidth="1">
            <path d="M0 44H820M0 110H820M0 176H820M0 242H820M0 308H820" />
            <path d="M0 0V308M102 0V308M204 0V308M306 0V308M408 0V308M510 0V308M612 0V308M714 0V308M819 0V308" />
          </g>

          <rect fill="url(#recovery-proof-window)" height="308" width="430" x="390" />
          <path
            d="M390 0V308"
            stroke="rgba(180,92,255,0.75)"
            strokeDasharray="5 6"
            strokeWidth="1.25"
          />
          <rect fill="#b45cff" height="5" width="5" x="387.5" y="10" />
          <text
            fill="rgba(212,177,255,0.8)"
            fontFamily="var(--font-geist-mono)"
            fontSize="9"
            letterSpacing="0.08em"
            x="402"
            y="18"
          >
            ROLLBACK OBSERVED · 14:18
          </text>

          <text
            fill="rgba(255,255,255,0.25)"
            fontFamily="var(--font-geist-mono)"
            fontSize="8"
            letterSpacing="0.08em"
            x="0"
            y="72"
          >
            FEATURE SCALE
          </text>
          <path
            d="M0 102H360L390 126H820"
            fill="none"
            stroke="#b45cff"
            strokeWidth="2"
          />
          <text fill="#d4b1ff" fontFamily="var(--font-geist-mono)" fontSize="9" x="8" y="95">
            ×100
          </text>
          <text fill="rgba(212,177,255,0.75)" fontFamily="var(--font-geist-mono)" fontSize="9" x="802" y="119" textAnchor="end">
            ×1
          </text>

          <text
            fill="rgba(255,255,255,0.25)"
            fontFamily="var(--font-geist-mono)"
            fontSize="8"
            letterSpacing="0.08em"
            x="0"
            y="188"
          >
            PRODUCTION RECALL
          </text>
          <path
            d="M0 248H820"
            fill="none"
            stroke="rgba(255,255,255,0.28)"
            strokeDasharray="7 7"
          />
          <text
            fill="rgba(255,255,255,0.28)"
            fontFamily="var(--font-geist-mono)"
            fontSize="9"
            x="812"
            y="239"
            textAnchor="end"
          >
            9.3%
          </text>
          <path
            d="M0 278 C70 280 130 275 195 278 S315 280 390 275 C450 267 493 250 540 230 S650 208 820 204"
            fill="none"
            stroke="#77d9a7"
            strokeWidth="2.25"
          />
          <circle cx="820" cy="204" fill="#77d9a7" r="3.5" />

          <g fill="#77d9a7" fillOpacity="0.52">
            <rect height="9" width="5" x="470" y="292" />
            <rect height="12" width="5" x="490" y="289" />
            <rect height="8" width="5" x="510" y="293" />
            <rect height="13" width="5" x="530" y="288" />
            <rect height="10" width="5" x="550" y="291" />
            <rect height="12" width="5" x="570" y="289" />
            <rect height="9" width="5" x="590" y="292" />
            <rect height="13" width="5" x="610" y="288" />
            <rect height="10" width="5" x="630" y="291" />
            <rect height="12" width="5" x="650" y="289" />
            <rect height="9" width="5" x="670" y="292" />
            <rect height="13" width="5" x="690" y="288" />
            <rect height="10" width="5" x="710" y="291" />
            <rect height="12" width="5" x="730" y="289" />
            <rect height="9" width="5" x="750" y="292" />
            <rect height="13" width="5" x="770" y="288" />
            <rect height="10" width="5" x="790" y="291" />
          </g>
        </svg>
      </div>

      <div className="grid grid-cols-2 border-t border-white/8 lg:grid-cols-4">
        <ProofCell label="Action result" tone="success" value="Succeeded" />
        <div className="border-l border-white/8">
          <ProofCell label="Observed state" tone="success" value="feature v1 · ×1" />
        </div>
        <div className="border-t border-white/8 lg:border-t-0 lg:border-l">
          <ProofCell label="Fresh window" value="240 labeled outcomes" />
        </div>
        <div className="border-t border-l border-white/8 lg:border-t-0">
          <ProofCell label="Incident" tone="success" value="Recovery verified" />
        </div>
      </div>

      <figcaption className="sr-only">
        After the feature rollback is observed, the scale multiplier returns to one and a new
        labeled monitor window shows production recall above the healthy boundary. The incident
        resolves only after the action result, runtime state, and fresh evidence agree.
      </figcaption>
    </figure>
  );
}
