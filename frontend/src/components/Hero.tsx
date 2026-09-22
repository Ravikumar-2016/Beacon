import { useState, type FormEvent } from "react";
import { ArrowRight, Bot, Compass, ShieldCheck } from "lucide-react";

interface Props {
  onSubmit: (url: string) => void;
  error: string | null;
  busy: boolean;
}

const FEATURES = [
  { icon: Bot, text: "Can AI systems discover & trust your content" },
  { icon: Compass, text: "Can visitors orient, navigate & take action" },
  { icon: ShieldCheck, text: "Read-only — never modifies your site" },
];

export default function Hero({ onSubmit, error, busy }: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim() || busy) return;
    onSubmit(value.trim());
  };

  return (
    <section className="mx-auto flex max-w-3xl flex-col items-center px-6 pb-20 pt-10 text-center sm:pt-16">
      <span className="animate-fade-up mb-6 inline-flex items-center gap-2 rounded-full border border-line bg-panel/60 px-3.5 py-1.5 text-xs text-ink-dim">
        <span className="h-1.5 w-1.5 rounded-full bg-good" style={{ animation: "pulse-glow 2s ease-in-out infinite" }} />
        Evidence-backed audits in under 5 minutes
      </span>

      <h1
        className="animate-fade-up font-display text-4xl font-semibold leading-[1.08] tracking-tight text-ink sm:text-6xl"
        style={{ animationDelay: "60ms" }}
      >
        Is your brand{" "}
        <span className="bg-gradient-to-r from-cyan via-violet to-magenta bg-clip-text text-transparent">
          visible to AI
        </span>
        —and ready for visitors?
      </h1>

      <p
        className="animate-fade-up mt-5 max-w-xl text-balance text-base leading-relaxed text-ink-dim sm:text-lg"
        style={{ animationDelay: "120ms" }}
      >
        Beacon crawls any public site, checks what AI assistants and human visitors actually
        experience, and hands you a prioritized, evidence-backed fix list.
      </p>

      <form
        onSubmit={handleSubmit}
        className="animate-fade-up mt-9 flex w-full max-w-lg flex-col gap-3 sm:flex-row"
        style={{ animationDelay: "180ms" }}
      >
        <input
          type="text"
          inputMode="url"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="yourbrand.com"
          className="w-full flex-1 rounded-xl border border-line bg-panel/80 px-4 py-3.5 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-cyan/50"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan to-violet px-5 py-3.5 text-sm font-semibold text-abyss transition-transform active:scale-[0.98] disabled:opacity-50"
        >
          Run audit
          <ArrowRight size={16} strokeWidth={2.5} />
        </button>
      </form>

      {error && (
        <p className="animate-fade-up mt-3 text-sm text-critical">{error}</p>
      )}

      <div
        className="animate-fade-up mt-12 flex flex-col gap-3 sm:flex-row sm:gap-6"
        style={{ animationDelay: "240ms" }}
      >
        {FEATURES.map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-center gap-2 text-xs text-ink-dim">
            <Icon size={15} className="text-cyan shrink-0" strokeWidth={2} />
            {text}
          </div>
        ))}
      </div>
    </section>
  );
}
