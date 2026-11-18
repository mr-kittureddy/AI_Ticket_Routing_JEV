import clsx from "clsx";
import { motion, useReducedMotion } from "framer-motion";
import { Zap } from "lucide-react";
import { formatMs, latencyTone, type LatencyTone } from "@/lib/format";

interface SpeedBadgeProps {
  /** Measured JEV classification time (jev_execution_time_ms). */
  latencyMs: number;
  /** Target from the backend (JEV_LATENCY_THRESHOLD_MS), normally 500. */
  thresholdMs: number;
  size?: "md" | "lg";
  className?: string;
}

const TONE_CLASSES: Record<LatencyTone, string> = {
  ok: "border-jev/50 bg-jev/10 text-jev shadow-glow-jev",
  warn: "border-warn/50 bg-warn/10 text-warn",
  bad: "border-bad/50 bg-bad/10 text-bad shadow-glow-bad",
};

export function SpeedBadge({ latencyMs, thresholdMs, size = "lg", className }: SpeedBadgeProps): JSX.Element {
  const reduceMotion = useReducedMotion();
  const tone = latencyTone(latencyMs, thresholdMs);
  const withinTarget = tone === "ok";

  return (
    <motion.div
      key={latencyMs}
      initial={reduceMotion ? false : { opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={clsx(
        "inline-flex flex-col items-start rounded-xl border",
        size === "lg" ? "gap-1 px-4 py-3" : "gap-0.5 px-3 py-2",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <Zap
          aria-hidden="true"
          className={clsx(size === "lg" ? "h-6 w-6" : "h-4 w-4", withinTarget && "animate-pulse-ring rounded-full")}
          fill={withinTarget ? "currentColor" : "none"}
        />
        <span
          className={clsx(
            "font-mono font-bold tabular-nums leading-none",
            size === "lg" ? "text-3xl" : "text-lg",
          )}
        >
          {formatMs(latencyMs)}
        </span>
      </div>
      <p className="text-xs font-medium">
        {withinTarget
          ? `Under the ${thresholdMs} ms target`
          : `Over the ${thresholdMs} ms target`}
      </p>
      {!withinTarget && (
        <p className="max-w-[16rem] text-xs text-ink-muted">
          A live OpenRouter call includes the network round trip, so it can exceed the target.
        </p>
      )}
    </motion.div>
  );
}
