export type Severity = "critical" | "high" | "medium" | "low";

export interface SuggestedAction {
  summary: string;
  priority: string;
}

export interface Finding {
  id: string;
  title: string;
  severity: Severity;
  evidence: string;
  suggested_action: SuggestedAction;
}

export interface ProactiveSuggestion {
  id: string;
  title: string;
  evidence: string;
  suggested_action: SuggestedAction;
}

export interface AuditSummary {
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
}

export interface AuditReport {
  site: string;
  audited_at: string;
  summary: AuditSummary;
  findings: Finding[];
  proactive_suggestions?: ProactiveSuggestion[];
  _diagnostics?: { specialist_errors: string[] };
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Job {
  id: string;
  url: string;
  status: JobStatus;
  created_at: number;
  finished_at: number | null;
  report: AuditReport | null;
  error: string | null;
}
