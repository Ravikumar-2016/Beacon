import { RotateCcw, Radar } from "lucide-react";

interface Props {
  onReset?: () => void;
  showReset: boolean;
}

export default function Header({ onReset, showReset }: Props) {
  return (
    <header className="relative z-10 flex items-center justify-between px-6 py-6 sm:px-10">
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan to-violet text-abyss">
          <Radar size={17} strokeWidth={2.5} />
        </div>
        <span className="font-display text-lg font-semibold tracking-tight text-ink">Beacon</span>
        <span className="hidden rounded-full border border-line px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-faint sm:inline">
          AI Readiness Audit
        </span>
      </div>

      {showReset && (
        <button
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-xs font-medium text-ink-dim transition-colors hover:border-cyan/40 hover:text-cyan"
        >
          <RotateCcw size={13} />
          New audit
        </button>
      )}
    </header>
  );
}
