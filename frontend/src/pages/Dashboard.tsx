import clsx from "clsx";
import { BarChart3, TriangleAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import { AppHeader } from "@/components/AppHeader";
import { EngineModeBadge } from "@/components/EngineModeBadge";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { useHealth } from "@/hooks/useHealth";
import { useProcessTicket } from "@/hooks/useProcessTicket";
import { TEAM_LABELS } from "@/lib/constants";
import { formatMs } from "@/lib/format";
import { DecisionPanel } from "@/panels/DecisionPanel";
import { JevSpotlightPanel } from "@/panels/JevSpotlightPanel";
import { OutputPanel } from "@/panels/OutputPanel";
import { TicketIngestionPanel } from "@/panels/TicketIngestionPanel";

/** The JEV latency target, used until the backend reports its configured threshold. */
const FALLBACK_THRESHOLD_MS = 500;
const NARROW_SCREEN_QUERY = "(max-width: 1023px)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function KnowledgeBaseBadge({ enabled }: { enabled: boolean | undefined }): JSX.Element {
  const label = enabled === undefined ? "Checking\u2026" : enabled ? "On" : "Off";
  const tone =
    enabled === true ? "border-ok/40 bg-ok/10 text-ok" : "border-line bg-raised text-ink-muted";
  const dot = enabled === true ? "bg-ok" : "bg-ink-subtle";

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tone,
      )}
    >
      <span aria-hidden="true" className={clsx("h-1.5 w-1.5 rounded-full", dot)} />
      <span>Knowledge base: {label}</span>
    </span>
  );
}

export function Dashboard(): JSX.Element {
  const health = useHealth();
  const mutation = useProcessTicket();
  const result = mutation.data ?? null;
  const isPending = mutation.isPending;

  const thresholdMs =
    result?.trace?.jev_threshold_ms ?? health.data?.jev_threshold_ms ?? FALLBACK_THRESHOLD_MS;

  // On narrow screens the results sit below the form, so bring them into view when a submit starts.
  const resultsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isPending) return;
    if (!window.matchMedia(NARROW_SCREEN_QUERY).matches) return;
    const reduceMotion = window.matchMedia(REDUCED_MOTION_QUERY).matches;
    resultsRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }, [isPending]);

  let announcement = "";
  if (isPending) {
    announcement = "Processing the ticket.";
  } else if (result !== null) {
    const { routing, resolution } = result.response;
    announcement =
      `Ticket ${result.response.ticket_id} routed to the ${TEAM_LABELS[routing.team]} team in ` +
      `${formatMs(routing.jev_execution_time_ms)}. ` +
      (routing.requires_action
        ? "Human action is required, so it was assigned to a human queue and Gemini was skipped."
        : `Gemini drafted the resolution in ${formatMs(resolution.gemini_execution_time_ms)}.`);
  }

  return (
    <div className="min-h-screen bg-canvas">
      <AppHeader
        title="IT Support AI Routing Dashboard"
        subtitle="JEV routes in milliseconds; Gemini drafts the answer only when no human action is needed"
        navTo="/analytics"
        navLabel="Analytics"
        navIcon={BarChart3}
      >
        <EngineModeBadge name="JEV" mode={health.data?.jev_engine_mode} />
        <EngineModeBadge name="Gemini" mode={health.data?.gemini_engine_mode} />
        <KnowledgeBaseBadge enabled={health.data?.rag_enabled} />
      </AppHeader>

      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-[1500px] px-4 py-6 focus:outline-none sm:px-6 lg:px-8"
      >
        <p role="status" className="sr-only">
          {announcement}
        </p>

        {health.isError && (
          <ErrorAlert
            error={health.error}
            title="The backend is not reachable"
            onRetry={() => void health.refetch()}
            className="mb-6"
          />
        )}

        {health.data?.status === "degraded" && (
          <div
            role="alert"
            className="mb-6 flex items-start gap-3 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm"
          >
            <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            <p className="text-ink-muted">
              <span className="font-medium text-ink">The database is unreachable.</span> Tickets cannot be saved
              until it is back, so submissions will fail.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-start">
          <div className="lg:sticky lg:top-6 lg:col-span-5">
            <TicketIngestionPanel
              isSubmitting={isPending}
              onSubmit={mutation.mutateAsync}
              onReset={mutation.reset}
            />
          </div>

          <div ref={resultsRef} className="scroll-mt-4 space-y-6 lg:col-span-7">
            <JevSpotlightPanel result={result} isPending={isPending} thresholdMs={thresholdMs} />
            <DecisionPanel result={result} isPending={isPending} />
            <OutputPanel result={result} isPending={isPending} />
          </div>
        </div>
      </main>
    </div>
  );
}
