export default function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="absolute -top-40 left-1/2 h-[560px] w-[560px] -translate-x-1/2 rounded-full opacity-30 blur-[110px]"
        style={{ background: "radial-gradient(circle, var(--color-cyan), transparent 70%)" }}
      />
      <div
        className="absolute -bottom-52 -left-32 h-[480px] w-[480px] rounded-full opacity-20 blur-[110px]"
        style={{ background: "radial-gradient(circle, var(--color-violet), transparent 70%)", animation: "float-slow 12s ease-in-out infinite" }}
      />
      <div
        className="absolute -right-40 top-1/3 h-[420px] w-[420px] rounded-full opacity-15 blur-[110px]"
        style={{ background: "radial-gradient(circle, var(--color-magenta), transparent 70%)", animation: "float-slow 15s ease-in-out infinite reverse" }}
      />
      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--color-ink) 1px, transparent 1px), linear-gradient(to bottom, var(--color-ink) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
        }}
      />
    </div>
  );
}
