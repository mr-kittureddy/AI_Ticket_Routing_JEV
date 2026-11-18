import clsx from "clsx";
import { Bot, Timer, UserRound } from "lucide-react";
import { EngineModeBadge } from "@/components/EngineModeBadge";
import { HumanQueueBadge } from "@/components/HumanQueueBadge";
import { ResolutionSteps } from "@/components/ResolutionSteps";
import { Card, type CardHighlight } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { STATUS_LABELS } from "@/lib/constants";
import { formatMs } from "@/lib/format";
import type { ProcessedTicket } from "@/types/ticket";

interface OutputPanelProps {
  result: ProcessedTicket | null;
  isPending: boolean;
}

export function OutputPanel({ result, isPending }: OutputPanelProps): JSX.Element {
  const requiresAction = result?.response.routing.requires_action ?? false;
  const highlight: CardHighlight = result === null ? "none" : requiresAction ? "human" : "gemini";

  return (
    <Card
      title="Gemini Output / Human Queue"
      subtitle="Where the ticket went and, when Gemini handled it, the drafted resolution"
      icon={requiresAction ? UserRound : Bot}
      highlight={highlight}
      bodyClassName="space-y-4"
    >
      {isPending ? (
        <div className="space-y-3" role="status" aria-label="Waiting for the resolution">
          <Skeleton className="h-7 w-48 rounded-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : result === null ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-ink-muted">
          Tickets that need a purchase, a physical install or admin approval go straight to a human queue. All others
          get a Gemini-drafted answer here.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {requiresAction ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1 text-xs font-medium text-ink-muted">
                <Timer aria-hidden="true" className="h-3.5 w-3.5" />
                Gemini execution: skipped (human action required)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-gemini/40 bg-gemini/10 px-3 py-1 text-xs font-medium text-ink">
                <Timer aria-hidden="true" className="h-3.5 w-3.5 text-gemini" />
                Gemini execution:{" "}
                <span className="font-mono tabular-nums">
                  {formatMs(result.response.resolution.gemini_execution_time_ms)}
                </span>
              </span>
            )}
            {result.trace !== null && !requiresAction && (
              <EngineModeBadge name="Gemini" engine={result.trace.gemini_engine} />
            )}
          </div>

          <p className="text-xs text-ink-muted">
            Status:{" "}
            <span
              className={clsx(
                "rounded-full px-2 py-0.5 font-mono text-xs font-semibold",
                requiresAction ? "bg-warn/15 text-warn" : "bg-ok/15 text-ok",
              )}
            >
              {result.response.resolution.status}
            </span>{" "}
            <span className="text-ink-subtle">({STATUS_LABELS[result.response.resolution.status]})</span>
            <span className="mx-1.5 text-ink-subtle" aria-hidden="true">
              &middot;
            </span>
            Handled by {result.response.resolution.handled_by}
          </p>

          {requiresAction ? (
            <HumanQueueBadge
              responseText={result.response.resolution.response_text}
              assignedQueue={result.trace?.assigned_queue ?? null}
            />
          ) : result.response.resolution.response_text !== null ? (
            <ResolutionSteps text={result.response.resolution.response_text} />
          ) : (
            <p className="text-sm text-ink-muted">Gemini returned no resolution text for this ticket.</p>
          )}
        </>
      )}
    </Card>
  );
}
