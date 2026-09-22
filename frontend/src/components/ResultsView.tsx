import { AlertTriangle, PartyPopper, Sparkles } from "lucide-react";
import type { AuditReport, Severity } from "../lib/types";
import { computeReadinessScore } from "../lib/score";
import ScoreRing from "./ScoreRing";
import SummaryStats from "./SummaryStats";
import FindingCard from "./FindingCard";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export default function ResultsView({ report }: { report: AuditReport }) {
  const score = computeReadinessScore(report.summary);
  const sortedFindings = [...report.findings].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
  );

  const audited = new Date(report.audited_at);
  const auditedLabel = Number.isNaN(audited.getTime())
    ? report.audited_at
    : audited.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <section className="mx-auto max-w-3xl px-6 pb-24">
      <div className="animate-fade-up rounded-2xl border border-line bg-panel/60 p-6 backdrop-blur-sm sm:p-8">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-8">
          <ScoreRing score={score} />
          <div className="flex-1 text-center sm:text-left">
            <p className="text-xs uppercase tracking-wide text-ink-faint">AI Readiness Report</p>
            <h2 className="mt-1 break-all font-display text-2xl font-semibold text-ink">{report.site}</h2>
            <p className="mt-1 text-xs text-ink-faint">Audited {auditedLabel}</p>
            <div className="mt-5">
              <SummaryStats summary={report.summary} />
            </div>
          </div>
        </div>
      </div>

      {report._diagnostics?.specialist_errors?.length ? (
        <div className="animate-fade-up mt-5 flex items-start gap-2.5 rounded-xl border border-high/30 bg-high/10 px-4 py-3 text-xs text-high">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            Some checks did not complete for this run, so the report below may be partial:{" "}
            {report._diagnostics.specialist_errors.join(" · ")}
          </span>
        </div>
      ) : null}

      <div className="mt-10">
        <h3 className="mb-4 font-display text-lg font-semibold text-ink">
          Findings <span className="text-ink-faint">({sortedFindings.length})</span>
        </h3>

        {sortedFindings.length === 0 ? (
          <div className="animate-fade-up flex items-center gap-3 rounded-2xl border border-good/30 bg-good/10 px-5 py-4 text-sm text-good">
            <PartyPopper size={18} />
            No issues found — this site is in great shape.
          </div>
        ) : (
          <div className="space-y-3">
            {sortedFindings.map((f, i) => (
              <FindingCard key={f.id} finding={f} index={i} />
            ))}
          </div>
        )}
      </div>

      {report.proactive_suggestions && report.proactive_suggestions.length > 0 && (
        <div className="mt-10">
          <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold text-ink">
            <Sparkles size={17} className="text-violet" />
            Opportunities
            <span className="text-ink-faint">({report.proactive_suggestions.length})</span>
          </h3>
          <div className="space-y-3">
            {report.proactive_suggestions.map((s, i) => (
              <FindingCard key={s.id} finding={s} proactive index={i} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
