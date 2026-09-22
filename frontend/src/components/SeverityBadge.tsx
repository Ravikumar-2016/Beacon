import type { Severity } from "../lib/types";

const CONFIG: Record<Severity, { label: string; color: string }> = {
  critical: { label: "Critical", color: "var(--color-critical)" },
  high: { label: "High", color: "var(--color-high)" },
  medium: { label: "Medium", color: "var(--color-medium)" },
  low: { label: "Low", color: "var(--color-low)" },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const cfg = CONFIG[severity] ?? CONFIG.medium;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide"
      style={{
        color: cfg.color,
        background: `color-mix(in oklab, ${cfg.color} 14%, transparent)`,
        border: `1px solid color-mix(in oklab, ${cfg.color} 35%, transparent)`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: cfg.color }} />
      {cfg.label}
    </span>
  );
}
