import clsx from "clsx";
import { ChevronDown, ChevronLeft, ChevronRight, History, Search } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useRole } from "@/context/RoleContext";
import { useTicketTrace, useTickets } from "@/hooks/useTickets";
import { DEFAULT_PAGE_SIZE, STATUS_LABELS, TEAM_COLORS, TEAM_LABELS } from "@/lib/constants";
import { formatCount, formatDateTime, formatMs, formatPercent, formatUsd } from "@/lib/format";
import { RESOLUTION_STATUSES, TARGET_TEAMS } from "@/schemas/ticket";
import type { ListTicketsParams, ResolutionStatus, TargetTeam, TicketRecord } from "@/types/ticket";
import { EngineModeBadge } from "./EngineModeBadge";
import { HumanQueueBadge } from "./HumanQueueBadge";
import { ResolutionSteps } from "./ResolutionSteps";
import { Card } from "./ui/Card";
import { ErrorAlert } from "./ui/ErrorAlert";
import { Skeleton } from "./ui/Skeleton";

const SEARCH_DEBOUNCE_MS = 300;
const COLUMN_COUNT = 10;
const SEARCH_MAX_LENGTH = 100;

type ActionFilter = "all" | "yes" | "no";

const FILTER_CONTROL_CLASSES =
  "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand";

const STATUS_BADGE: Record<ResolutionStatus, string> = {
  AUTO_RESOLVED: "bg-ok/15 text-ok",
  ASSIGNED_TO_HUMAN: "bg-warn/15 text-warn",
};

interface TraceDetailProps {
  ticket: TicketRecord;
}

/** Expanded row content. It is only mounted for an expanded row, so the trace is fetched on demand. */
function TraceDetail({ ticket }: TraceDetailProps): JSX.Element {
  const trace = useTicketTrace(ticket.ticket_id);
  const data = trace.data;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="min-w-0 space-y-4">
        <div>
          <h4 className="mb-1 text-xs font-medium text-ink">Ticket text</h4>
          <p className="whitespace-pre-wrap break-words text-sm text-ink-muted">{ticket.raw_text}</p>
        </div>
        {ticket.status === "ASSIGNED_TO_HUMAN" ? (
          <HumanQueueBadge responseText={ticket.response_text} assignedQueue={ticket.assigned_queue} />
        ) : ticket.response_text ? (
          <ResolutionSteps text={ticket.response_text} />
        ) : null}
      </div>

      <div className="min-w-0 space-y-3">
        <h4 className="text-xs font-medium text-ink">Routing trace</h4>

        {trace.isPending && (
          <div className="space-y-2" role="status" aria-label="Loading routing trace">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        )}

        {trace.isError && (
          <ErrorAlert
            error={trace.error}
            title="Could not load the routing trace"
            onRetry={() => void trace.refetch()}
          />
        )}

        {data !== undefined && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <EngineModeBadge name="JEV" engine={data.jev_engine} />
              <EngineModeBadge name="Gemini" engine={data.gemini_engine} />
            </div>

            <p className={clsx("text-xs font-medium", data.jev_within_threshold ? "text-ok" : "text-warn")}>
              JEV took {formatMs(data.jev_latency_ms)}, {data.jev_within_threshold ? "under" : "over"} the{" "}
              {data.jev_threshold_ms} ms target.
            </p>

            {data.gemini_bypassed && (
              <p className="text-xs text-ink-muted">
                Gemini was bypassed. Estimated saving: {formatMs(data.time_saved_ms)} and{" "}
                {formatUsd(data.cost_saved_usd)} (fixed baseline, not a measurement).
              </p>
            )}

            {data.rag_sources !== null && data.rag_sources.length > 0 && (
              <p className="text-xs text-ink-muted">
                Grounded with {data.rag_sources.length} similar past ticket
                {data.rag_sources.length === 1 ? "" : "s"}:{" "}
                <span className="font-mono text-ink-subtle">{data.rag_sources.join(", ")}</span>
              </p>
            )}

            <ul className="space-y-1.5">
              {data.decision_criteria.map((criterion, index) => (
                <li key={`${index}-${criterion}`} className="flex gap-2 text-xs text-ink-muted">
                  <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-subtle" />
                  <span className="min-w-0 break-words">{criterion}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

export function TicketHistoryTable(): JSX.Element {
  const { can } = useRole();

  const [page, setPage] = useState(1);
  const [team, setTeam] = useState<TargetTeam | "">("");
  const [status, setStatus] = useState<ResolutionStatus | "">("");
  const [action, setAction] = useState<ActionFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const params = useMemo<ListTicketsParams>(
    () => ({
      page,
      pageSize: DEFAULT_PAGE_SIZE,
      team: team === "" ? undefined : team,
      status: status === "" ? undefined : status,
      requiresHumanAction: action === "all" ? undefined : action === "yes",
      search: search === "" ? undefined : search,
    }),
    [page, team, status, action, search],
  );

  const query = useTickets(params);
  const data = query.data;
  const totalPages = data !== undefined ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  // If the data shrinks (for example after filtering elsewhere), pull the page back into range.
  useEffect(() => {
    if (data !== undefined && page > totalPages) setPage(totalPages);
  }, [data, page, totalPages]);

  const filtersActive = team !== "" || status !== "" || action !== "all" || search !== "";

  const resetPage = (): void => {
    setPage(1);
    setExpandedId(null);
  };

  if (!can("tickets:read")) {
    return (
      <Card title="Ticket history" icon={History}>
        <p className="text-sm text-ink-muted">
          Your current role cannot read tickets. Switch to Agent, Admin or Viewer to browse the history.
        </p>
      </Card>
    );
  }

  const from = data !== undefined && data.items.length > 0 ? (data.page - 1) * data.page_size + 1 : 0;
  const to = data !== undefined ? from + data.items.length - 1 : 0;

  return (
    <Card
      title="Ticket history"
      subtitle="Every processed ticket, newest first"
      icon={History}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-xs text-ink-muted">
          Search
          <span className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle"
            />
            <input
              type="search"
              value={searchInput}
              maxLength={SEARCH_MAX_LENGTH}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Ticket ID or text"
              className={clsx(FILTER_CONTROL_CLASSES, "w-full pl-8")}
            />
          </span>
        </label>

        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Team
          <select
            value={team}
            onChange={(event) => {
              setTeam(event.target.value as TargetTeam | "");
              resetPage();
            }}
            className={FILTER_CONTROL_CLASSES}
          >
            <option value="">All teams</option>
            {TARGET_TEAMS.map((value) => (
              <option key={value} value={value}>
                {TEAM_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as ResolutionStatus | "");
              resetPage();
            }}
            className={FILTER_CONTROL_CLASSES}
          >
            <option value="">All statuses</option>
            {RESOLUTION_STATUSES.map((value) => (
              <option key={value} value={value}>
                {STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Human action
          <select
            value={action}
            onChange={(event) => {
              setAction(event.target.value as ActionFilter);
              resetPage();
            }}
            className={FILTER_CONTROL_CLASSES}
          >
            <option value="all">Any</option>
            <option value="yes">Required</option>
            <option value="no">Not required</option>
          </select>
        </label>
      </div>

      {query.isError && (
        <ErrorAlert error={query.error} title="Could not load tickets" onRetry={() => void query.refetch()} />
      )}

      {query.isPending ? (
        <div className="space-y-2" role="status" aria-label="Loading tickets">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      ) : data !== undefined && data.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-ink-muted">
          {filtersActive
            ? "No tickets match these filters."
            : "No tickets have been processed yet. Submit one from the dashboard to see it here."}
        </p>
      ) : data !== undefined ? (
        <div className={clsx("overflow-x-auto rounded-lg border border-line", query.isPlaceholderData && "opacity-60")}>
          <table className="w-full min-w-[1040px] text-left text-xs">
            <thead className="bg-raised text-ink-muted">
              <tr>
                {[
                  "Ticket",
                  "Submitted by",
                  "Team",
                  "Status",
                  "Human action",
                  "Confidence",
                  "JEV",
                  "Gemini",
                  "Queue",
                  "Created",
                ].map((heading) => (
                  <th key={heading} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((ticket) => {
                const expanded = expandedId === ticket.ticket_id;
                const detailId = `trace-${ticket.ticket_id}`;
                return (
                  <Fragment key={ticket.ticket_id}>
                    <tr className="border-t border-line align-middle hover:bg-raised/60">
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={detailId}
                          onClick={() => setExpandedId(expanded ? null : ticket.ticket_id)}
                          className="inline-flex items-center gap-1 rounded font-mono text-ink hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                        >
                          {expanded ? (
                            <ChevronDown aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                          ) : (
                            <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                          )}
                          {ticket.ticket_id}
                        </button>
                      </td>
                      <td className="max-w-[12rem] truncate px-3 py-2 text-ink-muted" title={ticket.submitted_by}>
                        {ticket.submitted_by}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-ink">
                        <span className="inline-flex items-center gap-1.5">
                          <span
                            aria-hidden="true"
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: TEAM_COLORS[ticket.target_team] }}
                          />
                          {TEAM_LABELS[ticket.target_team]}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={clsx(
                            "inline-block whitespace-nowrap rounded-full px-2 py-0.5 font-medium",
                            STATUS_BADGE[ticket.status],
                          )}
                        >
                          {STATUS_LABELS[ticket.status]}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-ink">{ticket.requires_human_action ? "Yes" : "No"}</td>
                      <td className="px-3 py-2 font-mono tabular-nums text-ink">
                        {formatPercent(ticket.confidence_score)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
                        {formatMs(ticket.jev_latency_ms)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
                        {ticket.gemini_execution_time_ms !== null ? (
                          formatMs(ticket.gemini_execution_time_ms)
                        ) : (
                          <span className="font-sans text-ink-subtle">Bypassed</span>
                        )}
                      </td>
                      <td className="max-w-[12rem] truncate px-3 py-2 text-ink-muted" title={ticket.assigned_queue ?? undefined}>
                        {ticket.assigned_queue ?? "\u2013"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-ink-muted">{formatDateTime(ticket.created_at)}</td>
                    </tr>
                    {expanded && (
                      <tr id={detailId} className="border-t border-line bg-raised/40">
                        <td colSpan={COLUMN_COUNT} className="px-4 py-4">
                          <TraceDetail ticket={ticket} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {data !== undefined && data.total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-ink-muted" aria-live="polite">
            Showing {formatCount(from)}&ndash;{formatCount(to)} of {formatCount(data.total)}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setPage((current) => Math.max(1, current - 1));
                setExpandedId(null);
              }}
              disabled={page <= 1}
              className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ChevronLeft aria-hidden="true" className="h-3.5 w-3.5" />
              Previous
            </button>
            <span className="text-xs text-ink-muted">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => {
                setPage((current) => current + 1);
                setExpandedId(null);
              }}
              disabled={page >= totalPages || query.isPlaceholderData}
              className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
              <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
