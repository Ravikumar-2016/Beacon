import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";

const STEPS = [
  { label: "Checking robots.txt & crawl permissions", at: 0 },
  { label: "Crawling pages & rendering with a browser", at: 12 },
  { label: "Checking brand identity, freshness & corroboration", at: 42 },
  { label: "Evaluating on-site engagement & navigation", at: 68 },
  { label: "Deduplicating findings & compiling report", at: 88 },
];

interface Props {
  url: string;
  done: boolean;
}

export default function ProgressPanel({ url, done }: Props) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - start) / 1000), 200);
    return () => clearInterval(id);
  }, []);

  // Ease toward ~94% over ~100s, never quite reaching 100 until `done`.
  const eased = done ? 100 : Math.min(94, 94 * (1 - Math.exp(-elapsed / 42)));

  return (
    <div className="mx-auto w-full max-w-xl animate-fade-up">
      <div className="rounded-2xl border border-line bg-panel/70 p-6 backdrop-blur-sm sm:p-8">
        <div className="mb-1 flex items-center justify-between">
          <p className="font-mono text-xs text-ink-faint truncate pr-4">{url}</p>
          <p className="font-mono text-xs tabular-nums text-ink-dim shrink-0">{elapsed.toFixed(0)}s</p>
        </div>

        <div className="my-4 h-1.5 w-full overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan to-violet transition-[width] duration-500 ease-out"
            style={{ width: `${eased}%` }}
          />
        </div>

        <ul className="mt-6 space-y-3.5">
          {STEPS.map((step, i) => {
            const isDone = done || eased > step.at + 14 || (i < STEPS.length - 1 && eased > STEPS[i + 1].at);
            const isActive = !isDone && eased >= step.at;
            return (
              <li key={step.label} className="flex items-center gap-3">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors ${
                    isDone
                      ? "border-good bg-good/15 text-good"
                      : isActive
                        ? "border-cyan bg-cyan/10 text-cyan"
                        : "border-line text-ink-faint"
                  }`}
                >
                  {isDone ? (
                    <Check size={12} strokeWidth={3} />
                  ) : isActive ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  )}
                </span>
                <span
                  className={`text-sm transition-colors ${
                    isDone ? "text-ink-dim" : isActive ? "text-ink" : "text-ink-faint"
                  }`}
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <p className="mt-5 text-center text-xs text-ink-faint">
        A full audit crawls up to 15 pages and can take a few minutes. Feel free to keep this tab open.
      </p>
    </div>
  );
}
