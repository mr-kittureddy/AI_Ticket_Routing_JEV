import clsx from "clsx";
import { motion, useReducedMotion } from "framer-motion";
import { formatPercent } from "@/lib/format";

interface ConfidenceMeterProps {
  /** Confidence as a 0-1 ratio (jev_confidence). */
  value: number;
  label?: string;
  className?: string;
}

type Tone = "ok" | "warn" | "bad";

function toneFor(value: number): Tone {
  if (value >= 0.85) return "ok";
  if (value >= 0.6) return "warn";
  return "bad";
}

const BAR_CLASSES: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
};

export function ConfidenceMeter({ value, label = "Confidence", className }: ConfidenceMeterProps): JSX.Element {
  const reduceMotion = useReducedMotion();
  const clamped = Math.min(1, Math.max(0, value));
  const percent = Math.round(clamped * 100);

  return (
    <div className={className}>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-medium text-ink">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-ink">{formatPercent(clamped)}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent} percent`}
        className="h-2 overflow-hidden rounded-full bg-raised"
      >
        <motion.div
          className={clsx("h-full rounded-full", BAR_CLASSES[toneFor(clamped)])}
          initial={reduceMotion ? false : { width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
