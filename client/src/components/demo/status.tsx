type Tone = "neutral" | "success" | "warning" | "critical";

const tones: Record<Tone, string> = {
  neutral: "bg-white/34",
  success: "bg-success",
  warning: "bg-brand-soft",
  critical: "bg-critical",
};

export function Status({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-white/52">
      <span className={`size-1.5 ${tones[tone]}`} />
      {label}
    </span>
  );
}
