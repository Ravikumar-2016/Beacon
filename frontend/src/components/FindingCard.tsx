import { useState } from "react";
import { ChevronDown, Lightbulb } from "lucide-react";
import type { Finding, ProactiveSuggestion } from "../lib/types";
import SeverityBadge from "./SeverityBadge";

interface Props {
  finding: Finding | ProactiveSuggestion;
  proactive?: boolean;
  index?: number;
}

export default function FindingCard({ finding, proactive, index = 0 }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="animate-fade-up rounded-2xl border border-line bg-panel/60 backdrop-blur-sm transition-colors hover:border-[color-mix(in_oklab,var(--color-cyan)_35%,var(--color-line))]"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-4 px-5 py-4 text-left"
      >
        <span className="font-mono text-xs text-ink-faint shrink-0 w-14">{finding.id}</span>

        <span className="flex-1 font-medium text-ink leading-snug">{finding.title}</span>

        {proactive ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-violet/30 bg-violet/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-violet shrink-0">
            <Lightbulb size={12} strokeWidth={2.5} />
            Opportunity
          </span>
        ) : (
          <span className="shrink-0">
            <SeverityBadge severity={(finding as Finding).severity} />
          </span>
        )}

        <ChevronDown
          size={18}
          className={`shrink-0 text-ink-faint transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <div className="space-y-4 border-t border-line px-5 pb-5 pt-4">
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Evidence
              </p>
              <pre className="whitespace-pre-wrap rounded-lg border border-line bg-abyss/60 p-3 font-mono text-[12.5px] leading-relaxed text-ink-dim">
                {finding.evidence}
              </pre>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Suggested fix &middot;{" "}
                <span className="normal-case text-cyan">{finding.suggested_action.priority} priority</span>
              </p>
              <p className="text-sm leading-relaxed text-ink">{finding.suggested_action.summary}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
