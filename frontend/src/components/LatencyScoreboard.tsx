import clsx from "clsx";
import { Bot, Zap } from "lucide-react";
import { ENGINE_LABELS } from "@/lib/constants";
import { formatMs, formatSpeedMultiple, latencyTone } from "@/lib/format";

interface LatencyScoreboardProps {
  jevMs: number;
  thresholdMs: number;
  /** Gemini drafting time; null when Gemini was bypassed. */
  geminiMs: number | null;
  /** Browser-measured round trip for the whole request. */
  clientRoundTripMs?: number;
  /** Exact engine strings from the trace, when available. */
  jevEngine?: string;
  geminiEngine?: string;
  className?: string;
}

const MIN_BAR_PERCENT = 3;

const JEV_BAR: Record<ReturnType<typeof latencyTone>, string> = {
  ok: "bg-jev",
  warn: "bg-warn",
  bad: "bg-bad",
};

function barPercent(value: number, max: number): number {
  if (max <= 0) return MIN_BAR_PERCENT;
  return Math.min(100, Math.max(MIN_BAR_PERCENT, (value / max) * 100));
}

export function LatencyScoreboard({
  jevMs,
  thresholdMs,
  geminiMs,
  clientRoundTripMs,
  jevEngine,
  geminiEngine,
  className,
}: LatencyScoreboardProps): JSX.Element {
  const maxMs = Math.max(jevMs, geminiMs ?? 0);
  const multiple = geminiMs !== null ? formatSpeedMultiple(geminiMs, jevMs) : null;
  const tone = latencyTone(jevMs, thresholdMs);

  return (
    <div className={clsx("space-y-3", className)}>
      <div>
        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 font-medium text-ink">
            <Zap aria-hidden="true" className="h-3.5 w-3.5 text-jev" />
            JEV classification
            {jevEngine !== undefined && (
              <span className="font-normal text-ink-subtle">({ENGINE_LABELS[jevEngine] ?? jevEngine})</span>
            )}
          </span>
          <span className="font-mono tabular-nums text-ink">{formatMs(jevMs)}</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-raised" aria-hidden="true">
          <div
            className={clsx("h-full rounded-full transition-all duration-700", JEV_BAR[tone])}
            style={{ width: `${barPercent(jevMs, maxMs)}%` }}
          />
        </div>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 font-medium text-ink">
            <Bot aria-hidden="true" className="h-3.5 w-3.5 text-gemini" />
            Gemini drafting
            {geminiEngine !== undefined && geminiEngine !== "bypassed" && (
              <span className="font-normal text-ink-subtle">({ENGINE_LABELS[geminiEngine] ?? geminiEngine})</span>
            )}
          </span>
          <span className="font-mono tabular-nums text-ink">
            {geminiMs !== null ? formatMs(geminiMs) : "Bypassed"}
          </span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-raised" aria-hidden="true">
          {geminiMs !== null && (
            <div
              className="h-full rounded-full bg-gemini transition-all duration-700"
              style={{ width: `${barPercent(geminiMs, maxMs)}%` }}
            />
          )}
        </div>
      </div>

      <p className="text-xs text-ink-muted">
        {geminiMs === null
          ? "Gemini was skipped, so no generation time was spent on this ticket."
          : multiple !== null
            ? `JEV routed this ticket ${multiple} than Gemini drafted its answer.`
            : "JEV was not faster than Gemini on this ticket."}
      </p>

      {clientRoundTripMs !== undefined && (
        <p className="border-t border-line pt-2 text-xs text-ink-subtle">
          Browser round trip: <span className="font-mono tabular-nums">{formatMs(clientRoundTripMs)}</span>{" "}
          (network and the full pipeline, not just JEV)
        </p>
      )}
    </div>
  );
}
