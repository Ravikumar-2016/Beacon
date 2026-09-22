import type { AuditSummary } from "../lib/types";

interface Props {
  summary: AuditSummary;
}

export default function SummaryStats({ summary }: Props) {
  const low = Math.max(0, summary.total_findings - summary.critical - summary.high - summary.medium);
  const rows = [
    { label: "Critical", value: summary.critical, color: "var(--color-critical)" },
    { label: "High", value: summary.high, color: "var(--color-high)" },
    { label: "Medium", value: summary.medium, color: "var(--color-medium)" },
    { label: "Low", value: low, color: "var(--color-low)" },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {rows.map((r) => (
        <div key={r.label} className="rounded-xl border border-line bg-panel/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: r.color }} />
            <span className="text-xs uppercase tracking-wide text-ink-faint">{r.label}</span>
          </div>
          <p className="mt-1.5 font-display text-2xl font-semibold text-ink">{r.value}</p>
        </div>
      ))}
    </div>
  );
}
