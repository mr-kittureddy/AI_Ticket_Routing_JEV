import { Zap } from "lucide-react";
import { LatencyScoreboard } from "@/components/LatencyScoreboard";
import { SavingsCallout } from "@/components/SavingsCallout";
import { SpeedBadge } from "@/components/SpeedBadge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ProcessedTicket } from "@/types/ticket";

interface JevSpotlightPanelProps {
  result: ProcessedTicket | null;
  isPending: boolean;
  /** The JEV latency target (from the trace or the health endpoint; 500 ms by default). */
  thresholdMs: number;
}

export function JevSpotlightPanel({ result, isPending, thresholdMs }: JevSpotlightPanelProps): JSX.Element {
  return (
    <Card
      title="JEV AI Performance Spotlight"
      subtitle={`Classification speed against the ${thresholdMs} ms target`}
      icon={Zap}
      highlight="jev"
      bodyClassName="space-y-4"
    >
      {isPending ? (
        <div className="space-y-4" role="status" aria-label="JEV is classifying the ticket">
          <Skeleton className="h-24 w-44 rounded-xl" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : result === null ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-ink-muted">
          Submit a ticket to see how quickly JEV classifies it, and how that compares with a Gemini draft.
        </p>
      ) : (
        <>
          <SpeedBadge latencyMs={result.response.routing.jev_execution_time_ms} thresholdMs={thresholdMs} />

          <LatencyScoreboard
            jevMs={result.response.routing.jev_execution_time_ms}
            thresholdMs={thresholdMs}
            geminiMs={result.response.resolution.gemini_execution_time_ms}
            clientRoundTripMs={result.clientRoundTripMs}
            jevEngine={result.trace?.jev_engine}
            geminiEngine={result.trace?.gemini_engine}
          />

          {result.trace !== null && result.trace.jev_engine.startsWith("simulator") && (
            <p className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-ink-muted">
              JEV ran in simulator mode: a deterministic local rule engine, with no LLM call and no network. Its time
              shows the rules are fast, not what a live OpenRouter call will take.
            </p>
          )}

          <SavingsCallout
            bypassed={result.response.routing.requires_action}
            timeSavedMs={result.trace?.time_saved_ms ?? null}
            costSavedUsd={result.trace?.cost_saved_usd ?? null}
          />
        </>
      )}
    </Card>
  );
}
