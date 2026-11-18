import clsx from "clsx";
import { Coins, Timer, Zap } from "lucide-react";
import { formatMs, formatUsd } from "@/lib/format";

interface SavingsCalloutProps {
  /** True when Gemini was bypassed because the ticket needs human action. */
  bypassed: boolean;
  /** Estimated time saved; null when the trace could not be loaded. */
  timeSavedMs: number | null;
  /** Estimated cost saved; null when the trace could not be loaded. */
  costSavedUsd: number | null;
  className?: string;
}

export function SavingsCallout({
  bypassed,
  timeSavedMs,
  costSavedUsd,
  className,
}: SavingsCalloutProps): JSX.Element {
  if (!bypassed) {
    return (
      <div className={clsx("rounded-lg border border-line bg-raised p-3 text-sm text-ink-muted", className)}>
        <p className="font-medium text-ink">Gemini resolved this ticket</p>
        <p className="mt-0.5 text-xs">
          No LLM call was avoided here. Savings are counted when JEV routes a ticket that needs human action
          straight to a queue.
        </p>
      </div>
    );
  }

  return (
    <div className={clsx("rounded-lg border border-jev/40 bg-jev/10 p-3", className)}>
      <p className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Zap aria-hidden="true" className="h-4 w-4 text-jev" fill="currentColor" />
        Instant Routing Completed without LLM Overhead
      </p>

      {timeSavedMs !== null && costSavedUsd !== null ? (
        <dl className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-ink-muted">
              <Timer aria-hidden="true" className="h-3.5 w-3.5" />
              Time saved (est.)
            </dt>
            <dd className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-ink">{formatMs(timeSavedMs)}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-xs text-ink-muted">
              <Coins aria-hidden="true" className="h-3.5 w-3.5" />
              Cost saved (est.)
            </dt>
            <dd className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-ink">
              {formatUsd(costSavedUsd)}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="mt-2 text-xs text-ink-muted">
          Savings detail needs permission to read tickets, so only the routing result is shown for this role.
        </p>
      )}

      <p className="mt-3 text-xs text-ink-subtle">
        Estimates use a fixed per-ticket baseline for a Gemini draft. They are not measurements of this request.
      </p>
    </div>
  );
}
