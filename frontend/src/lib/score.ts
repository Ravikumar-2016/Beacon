import type { AuditSummary } from "./types";

const WEIGHTS = { critical: 26, high: 13, medium: 6, low: 2 } as const;

export function computeReadinessScore(summary: AuditSummary): number {
  const low = Math.max(0, summary.total_findings - summary.critical - summary.high - summary.medium);
  const penalty =
    summary.critical * WEIGHTS.critical +
    summary.high * WEIGHTS.high +
    summary.medium * WEIGHTS.medium +
    low * WEIGHTS.low;
  return Math.max(2, Math.round(100 - penalty));
}

export function scoreLabel(score: number): { label: string; color: string } {
  if (score >= 90) return { label: "Excellent", color: "var(--color-good)" };
  if (score >= 75) return { label: "Solid", color: "var(--color-cyan)" };
  if (score >= 55) return { label: "Needs work", color: "var(--color-medium)" };
  if (score >= 35) return { label: "At risk", color: "var(--color-high)" };
  return { label: "Critical", color: "var(--color-critical)" };
}
