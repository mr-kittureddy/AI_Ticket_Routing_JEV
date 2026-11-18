import clsx from "clsx";
import { ChevronDown, ChevronUp, ListChecks, ShieldCheck, UserRound } from "lucide-react";
import { useId, useState } from "react";
import { TEAM_LABELS } from "@/lib/constants";
import type { RoutingInfo, TicketTrace } from "@/types/ticket";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { EngineModeBadge } from "./EngineModeBadge";

interface DecisionVisualizerProps {
  routing: RoutingInfo;
  /** Null when the trace could not be loaded, for example when the role cannot read tickets. */
  trace: TicketTrace | null;
  className?: string;
}

const COLLAPSED_CRITERIA_COUNT = 3;

export function DecisionVisualizer({ routing, trace, className }: DecisionVisualizerProps): JSX.Element {
  // The parent should give this component a `key` of the ticket id so the expanded state resets per ticket.
  const [expanded, setExpanded] = useState(false);
  const criteriaListId = useId();

  const criteria = trace?.decision_criteria ?? [];
  const visibleCriteria = expanded ? criteria : criteria.slice(0, COLLAPSED_CRITERIA_COUNT);
  const hiddenCount = criteria.length - COLLAPSED_CRITERIA_COUNT;

  const decisionJson = JSON.stringify(
    {
      target_team: routing.team,
      requires_human_action: routing.requires_action,
      confidence_score: routing.jev_confidence,
      jev_latency_ms: routing.jev_execution_time_ms,
    },
    null,
    2,
  );

  return (
    <div className={clsx("space-y-4", className)}>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-line bg-raised p-3">
          <dt className="text-xs text-ink-muted">Assigned team</dt>
          <dd className="mt-1 text-sm font-semibold text-ink">{TEAM_LABELS[routing.team]}</dd>
          <dd className="mt-0.5 font-mono text-xs text-ink-subtle">{routing.team}</dd>
        </div>

        <div className="rounded-lg border border-line bg-raised p-3">
          <dt className="text-xs text-ink-muted">Action required</dt>
          <dd className="mt-1">
            <span
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide",
                routing.requires_action ? "bg-warn/15 text-warn" : "bg-ok/15 text-ok",
              )}
            >
              {routing.requires_action ? (
                <UserRound aria-hidden="true" className="h-3.5 w-3.5" />
              ) : (
                <ShieldCheck aria-hidden="true" className="h-3.5 w-3.5" />
              )}
              {routing.requires_action ? "TRUE" : "FALSE"}
            </span>
          </dd>
          <dd className="mt-1 text-xs text-ink-subtle">
            {routing.requires_action
              ? "Purchase, physical install or admin privilege needed"
              : "Safe to resolve with informational steps"}
          </dd>
        </div>
      </dl>

      <ConfidenceMeter value={routing.jev_confidence} label="JEV confidence" />

      {trace !== null && (
        <div className="flex flex-wrap items-center gap-2">
          <EngineModeBadge name="JEV" engine={trace.jev_engine} />
          <EngineModeBadge name="Gemini" engine={trace.gemini_engine} />
        </div>
      )}

      <div>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink">
          <ListChecks aria-hidden="true" className="h-3.5 w-3.5 text-ink-muted" />
          Decision criteria
        </h3>
        {trace === null ? (
          <p className="text-xs text-ink-muted">
            The criteria come from the routing trace, which needs permission to read tickets. The routing result
            above is unaffected.
          </p>
        ) : criteria.length === 0 ? (
          <p className="text-xs text-ink-muted">No criteria were recorded for this ticket.</p>
        ) : (
          <>
            <ul id={criteriaListId} className="space-y-1.5">
              {visibleCriteria.map((criterion, index) => (
                <li key={`${index}-${criterion}`} className="flex gap-2 text-xs text-ink-muted">
                  <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-subtle" />
                  <span className="min-w-0 break-words">{criterion}</span>
                </li>
              ))}
            </ul>
            {hiddenCount > 0 && (
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={criteriaListId}
                onClick={() => setExpanded((current) => !current)}
                className="mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                {expanded ? (
                  <>
                    <ChevronUp aria-hidden="true" className="h-3.5 w-3.5" />
                    Show fewer
                  </>
                ) : (
                  <>
                    <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" />
                    Show {hiddenCount} more
                  </>
                )}
              </button>
            )}
          </>
        )}
      </div>

      <div>
        <h3 className="mb-1.5 text-xs font-medium text-ink">JEV decision output</h3>
        <pre
          tabIndex={0}
          aria-label="JEV decision output as JSON"
          className="overflow-x-auto rounded-lg border border-line bg-raised p-3 font-mono text-xs leading-relaxed text-ink-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {decisionJson}
        </pre>
      </div>
    </div>
  );
}
