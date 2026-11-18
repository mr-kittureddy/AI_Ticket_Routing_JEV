import clsx from "clsx";
import {
  ArrowLeft,
  Bot,
  Coins,
  Gauge,
  Percent,
  Table2,
  Target,
  Ticket,
  Timer,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "@/components/AppHeader";
import { CostSavingsChart } from "@/components/CostSavingsChart";
import { LatencyChart } from "@/components/LatencyChart";
import { ReportExportButtons } from "@/components/ReportExportButtons";
import { TicketHistoryTable } from "@/components/TicketHistoryTable";
import { Card } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { Skeleton } from "@/components/ui/Skeleton";
import { useRole } from "@/context/RoleContext";
import { useAnalytics } from "@/hooks/useAnalytics";
import { ANALYTICS_WINDOW_OPTIONS, DEFAULT_SERIES_LIMIT, TEAM_COLORS, TEAM_LABELS } from "@/lib/constants";
import { formatCount, formatDateTime, formatMs, formatPercent, formatUsd } from "@/lib/format";

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
}

function StatCard({ label, value, hint, icon: Icon }: StatCardProps): JSX.Element {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink-muted">{label}</p>
        <Icon aria-hidden="true" className="h-4 w-4 text-ink-subtle" />
      </div>
      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-ink">{value}</p>
      {hint !== undefined && <p className="mt-1 text-xs text-ink-subtle">{hint}</p>}
    </div>
  );
}

export function AnalyticsPage(): JSX.Element {
  const { can } = useRole();
  const windowSelectId = useId();
  const [windowIndex, setWindowIndex] = useState(0);

  const windowOption = ANALYTICS_WINDOW_OPTIONS[windowIndex] ?? ANALYTICS_WINDOW_OPTIONS[0];
  const windowDays = windowOption.value;

  const analytics = useAnalytics({ windowDays });
  const data = analytics.data;
  const allowed = can("analytics:read");

  return (
    <div className="min-h-screen bg-canvas">
      <AppHeader
        title="Analytics"
        subtitle="JEV speed, Gemini bypass rate and estimated savings"
        navTo="/"
        navLabel="Dashboard"
        navIcon={ArrowLeft}
      />

      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-[1500px] space-y-6 px-4 py-6 focus:outline-none sm:px-6 lg:px-8"
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <label htmlFor={windowSelectId} className="mb-1 block text-xs font-medium text-ink">
              Time window
            </label>
            <select
              id={windowSelectId}
              value={windowIndex}
              onChange={(event) => setWindowIndex(Number(event.target.value))}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {ANALYTICS_WINDOW_OPTIONS.map((option, index) => (
                <option key={option.label} value={index}>
                  {option.label}
                </option>
              ))}
            </select>
            {data !== undefined && (
              <p className="mt-1 text-xs text-ink-subtle" aria-live="polite">
                {analytics.isPlaceholderData ? "Updating\u2026" : `Updated ${formatDateTime(data.generated_at)}`}
              </p>
            )}
          </div>

          <ReportExportButtons windowDays={windowDays} />
        </div>

        {!allowed ? (
          <Card title="Analytics" icon={Gauge}>
            <p className="text-sm text-ink-muted">
              Your current role cannot read analytics. Use the role selector in the header to switch.
            </p>
          </Card>
        ) : (
          <>
            {analytics.isError && (
              <ErrorAlert
                error={analytics.error}
                title="Could not load analytics"
                onRetry={() => void analytics.refetch()}
              />
            )}

            {analytics.isPending && (
              <div role="status" aria-label="Loading analytics" className="space-y-6">
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  {Array.from({ length: 8 }, (_, index) => (
                    <Skeleton key={index} className="h-28 w-full rounded-xl" />
                  ))}
                </div>
                <Skeleton className="h-80 w-full rounded-xl" />
                <Skeleton className="h-80 w-full rounded-xl" />
              </div>
            )}

            {data !== undefined && (
              <div className={clsx("space-y-6 transition-opacity", analytics.isPlaceholderData && "opacity-60")}>
                {data.summary.total_tickets === 0 && (
                  <div className="rounded-lg border border-dashed border-line bg-surface px-4 py-6 text-center text-sm text-ink-muted">
                    No tickets were processed in this window.{" "}
                    <Link to="/" className="font-medium text-brand hover:underline">
                      Submit one from the dashboard
                    </Link>{" "}
                    to see statistics here.
                  </div>
                )}

                <section aria-label="Summary statistics" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  <StatCard
                    label="Tickets processed"
                    value={formatCount(data.summary.total_tickets)}
                    hint={`${formatCount(data.summary.auto_resolved_count)} auto-resolved`}
                    icon={Ticket}
                  />
                  <StatCard
                    label="Gemini bypass rate"
                    value={formatPercent(data.summary.gemini_bypass_rate, 1)}
                    hint={`${formatCount(data.summary.assigned_to_human_count)} sent straight to humans`}
                    icon={Percent}
                  />
                  <StatCard
                    label="Average JEV latency"
                    value={formatMs(data.summary.avg_jev_latency_ms)}
                    hint={`p50 ${formatMs(data.summary.p50_jev_latency_ms)} \u00b7 p95 ${formatMs(data.summary.p95_jev_latency_ms)}`}
                    icon={Zap}
                  />
                  <StatCard
                    label="JEV within target"
                    value={formatPercent(data.summary.jev_within_threshold_rate, 1)}
                    hint={`Under ${data.summary.jev_threshold_ms} ms`}
                    icon={Target}
                  />
                  <StatCard
                    label="Average Gemini latency"
                    value={formatMs(data.summary.avg_gemini_latency_ms)}
                    hint="Tickets Gemini resolved"
                    icon={Bot}
                  />
                  <StatCard
                    label="Average JEV confidence"
                    value={formatPercent(data.summary.avg_confidence, 1)}
                    icon={Gauge}
                  />
                  <StatCard
                    label="Time saved (estimated)"
                    value={formatMs(data.summary.total_time_saved_ms)}
                    hint="Fixed baseline per bypassed ticket"
                    icon={Timer}
                  />
                  <StatCard
                    label="Cost saved (estimated)"
                    value={formatUsd(data.summary.total_cost_saved_usd)}
                    hint="Fixed baseline per bypassed ticket"
                    icon={Coins}
                  />
                </section>

                <Card
                  title="JEV vs Gemini latency"
                  subtitle={`Latest ${DEFAULT_SERIES_LIMIT} tickets in this window`}
                  icon={Zap}
                  highlight="jev"
                >
                  <LatencyChart points={data.latency_series} thresholdMs={data.summary.jev_threshold_ms} />
                </Card>

                <Card
                  title="Savings from bypassing Gemini"
                  subtitle={`Latest ${DEFAULT_SERIES_LIMIT} tickets; running totals cover the whole window`}
                  icon={Coins}
                >
                  <CostSavingsChart points={data.savings_series} />
                </Card>

                <Card title="Team breakdown" subtitle="Where tickets were routed" icon={Table2}>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead className="text-xs text-ink-muted">
                        <tr>
                          <th scope="col" className="py-2 pr-3 font-medium">
                            Team
                          </th>
                          <th scope="col" className="px-3 py-2 font-medium">
                            Share
                          </th>
                          <th scope="col" className="px-3 py-2 text-right font-medium">
                            Total
                          </th>
                          <th scope="col" className="px-3 py-2 text-right font-medium">
                            Auto-resolved
                          </th>
                          <th scope="col" className="px-3 py-2 text-right font-medium">
                            Human
                          </th>
                          <th scope="col" className="py-2 pl-3 text-right font-medium">
                            Avg JEV
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.team_breakdown.map((item) => {
                          const share =
                            data.summary.total_tickets > 0 ? item.total / data.summary.total_tickets : 0;
                          return (
                            <tr key={item.team} className="border-t border-line">
                              <td className="whitespace-nowrap py-2.5 pr-3 text-ink">
                                <span className="inline-flex items-center gap-2">
                                  <span
                                    aria-hidden="true"
                                    className="h-2.5 w-2.5 rounded-full"
                                    style={{ backgroundColor: TEAM_COLORS[item.team] }}
                                  />
                                  {TEAM_LABELS[item.team]}
                                </span>
                              </td>
                              <td className="px-3 py-2.5">
                                <div className="flex items-center gap-2">
                                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-raised" aria-hidden="true">
                                    <div
                                      className="h-full rounded-full"
                                      style={{
                                        width: `${Math.round(share * 100)}%`,
                                        backgroundColor: TEAM_COLORS[item.team],
                                      }}
                                    />
                                  </div>
                                  <span className="font-mono text-xs tabular-nums text-ink-muted">
                                    {formatPercent(share)}
                                  </span>
                                </div>
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink">
                                {formatCount(item.total)}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink">
                                {formatCount(item.auto_resolved)}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink">
                                {formatCount(item.assigned_to_human)}
                              </td>
                              <td className="py-2.5 pl-3 text-right font-mono tabular-nums text-ink">
                                {item.total > 0 ? formatMs(item.avg_jev_latency_ms) : "\u2013"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            )}
          </>
        )}

        <div className="space-y-2">
          <TicketHistoryTable />
          <p className="text-xs text-ink-subtle">
            The ticket history always lists every processed ticket; the time window above applies to the statistics,
            charts and exported reports.
          </p>
        </div>
      </main>
    </div>
  );
}
