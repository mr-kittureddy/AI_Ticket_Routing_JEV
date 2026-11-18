import clsx from "clsx";
import { ENGINE_LABELS } from "@/lib/constants";
import type { EngineMode } from "@/types/ticket";

type Tone = "ok" | "warn" | "neutral";

interface EngineModeBadgeProps {
  /** Engine name shown before the mode, for example "JEV" or "Gemini". */
  name: string;
  /** Mode from GET /api/health. */
  mode?: EngineMode;
  /** Exact engine string from a ticket trace; takes precedence over `mode`. */
  engine?: string;
  className?: string;
}

const TONE_CLASSES: Record<Tone, { badge: string; dot: string }> = {
  ok: { badge: "border-ok/40 bg-ok/10 text-ok", dot: "bg-ok" },
  warn: { badge: "border-warn/40 bg-warn/10 text-warn", dot: "bg-warn" },
  neutral: { badge: "border-line bg-raised text-ink-muted", dot: "bg-ink-subtle" },
};

function toneForEngine(engine: string): Tone {
  if (engine === "openrouter" || engine === "gemini") return "ok";
  if (engine === "bypassed") return "neutral";
  return "warn";
}

export function EngineModeBadge({ name, mode, engine, className }: EngineModeBadgeProps): JSX.Element {
  let label: string;
  let tone: Tone;

  if (engine !== undefined) {
    label = ENGINE_LABELS[engine] ?? engine;
    tone = toneForEngine(engine);
  } else if (mode === "live") {
    label = "Live";
    tone = "ok";
  } else if (mode === "simulated") {
    label = "Simulated";
    tone = "warn";
  } else {
    label = "Checking\u2026";
    tone = "neutral";
  }

  const styles = TONE_CLASSES[tone];

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        styles.badge,
        className,
      )}
    >
      <span aria-hidden="true" className={clsx("h-1.5 w-1.5 rounded-full", styles.dot)} />
      <span>
        {name}: {label}
      </span>
    </span>
  );
}
