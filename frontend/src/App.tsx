import { useCallback, useRef, useState } from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";
import Header from "./components/Header";
import Hero from "./components/Hero";
import ProgressPanel from "./components/ProgressPanel";
import ResultsView from "./components/ResultsView";
import Backdrop from "./components/Backdrop";
import { createAudit, pollAudit, ApiError } from "./lib/api";
import type { AuditReport } from "./lib/types";

type View = "idle" | "loading" | "results" | "error";

function normalizeUrl(input: string): string {
  const trimmed = input.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export default function App() {
  const [view, setView] = useState<View>("idle");
  const [targetUrl, setTargetUrl] = useState("");
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobDone, setJobDone] = useState(false);
  const inFlight = useRef(false);

  const runAudit = useCallback(async (rawUrl: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const url = normalizeUrl(rawUrl);
    setTargetUrl(url);
    setError(null);
    setJobDone(false);
    setView("loading");

    try {
      const { id } = await createAudit(url);
      const job = await pollAudit(id, (j) => {
        if (j.status === "done" || j.status === "error") setJobDone(true);
      });

      if (job.status === "done" && job.report) {
        setReport(job.report);
        setView("results");
      } else {
        setError(job.error || "The audit could not be completed.");
        setView("error");
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setView("error");
    } finally {
      inFlight.current = false;
    }
  }, []);

  const reset = useCallback(() => {
    setView("idle");
    setReport(null);
    setError(null);
    setTargetUrl("");
  }, []);

  return (
    <div className="relative min-h-screen">
      <Backdrop />
      <Header showReset={view !== "idle"} onReset={reset} />

      <main className="pt-6 sm:pt-10">
        {view === "idle" && <Hero onSubmit={runAudit} error={null} busy={false} />}

        {view === "loading" && (
          <div className="px-6 py-10 sm:py-16">
            <ProgressPanel url={targetUrl} done={jobDone} />
          </div>
        )}

        {view === "error" && (
          <div className="mx-auto flex max-w-md flex-col items-center px-6 py-20 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-critical/30 bg-critical/10 text-critical">
              <AlertOctagon size={22} />
            </div>
            <h2 className="mt-5 font-display text-xl font-semibold text-ink">Audit couldn't complete</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-dim">{error}</p>
            <button
              onClick={reset}
              className="mt-7 inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-cyan to-violet px-5 py-2.5 text-sm font-semibold text-abyss"
            >
              <RotateCcw size={14} />
              Try another site
            </button>
          </div>
        )}

        {view === "results" && report && <ResultsView report={report} />}
      </main>

      <footer className="px-6 pb-10 text-center text-xs text-ink-faint">
        Beacon audits publicly accessible pages only — read-only, no logins, no form submissions.
      </footer>
    </div>
  );
}
