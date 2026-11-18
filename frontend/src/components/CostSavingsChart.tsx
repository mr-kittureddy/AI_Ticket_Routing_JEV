import clsx from "clsx";
import { useId, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatMs, formatTimeOfDay, formatUsd } from "@/lib/format";
import type { SavingsPoint } from "@/types/ticket";

interface CostSavingsChartProps {
  points: SavingsPoint[];
  className?: string;
}

type Metric = "time" | "cost";

const AREA_COLOR = "#14b8a6";

interface Datum {
  ticketId: string;
  time: string;
  cumulative: number;
  step: number;
}

const METRIC_LABELS: Record<Metric, string> = {
  time: "Time saved",
  cost: "Cost saved",
};

function formatValue(metric: Metric, value: number): string {
  return metric === "time" ? formatMs(value) : formatUsd(value);
}

interface SavingsTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: Datum }>;
  metric: Metric;
}

function SavingsTooltip({ active, payload, metric }: SavingsTooltipProps): JSX.Element | null {
  const datum = payload?.[0]?.payload;
  if (!active || datum === undefined) return null;

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card">
      <p className="font-mono font-semibold text-ink">{datum.ticketId}</p>
      <p className="text-ink-subtle">{datum.time}</p>
      <dl className="mt-1.5 space-y-0.5">
        <div className="flex justify-between gap-6">
          <dt className="text-ink-muted">Saved on this ticket (est.)</dt>
          <dd className="font-mono tabular-nums text-ink">{formatValue(metric, datum.step)}</dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt className="text-ink-muted">Cumulative (est.)</dt>
          <dd className="font-mono tabular-nums text-ink">{formatValue(metric, datum.cumulative)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function CostSavingsChart({ points, className }: CostSavingsChartProps): JSX.Element {
  const [metric, setMetric] = useState<Metric>("time");
  // useId() returns values like ":r1:"; colons are not safe inside an SVG url(#...) reference.
  const gradientId = `savings-fill-${useId().replace(/:/g, "")}`;

  const data = useMemo<Datum[]>(
    () =>
      points.map((point) => ({
        ticketId: point.ticket_id,
        time: formatTimeOfDay(point.created_at),
        cumulative: metric === "time" ? point.cumulative_time_saved_ms : point.cumulative_cost_saved_usd,
        step: metric === "time" ? point.time_saved_ms : point.cost_saved_usd,
      })),
    [points, metric],
  );

  const timeByTicket = useMemo(() => new Map(data.map((datum) => [datum.ticketId, datum.time])), [data]);

  if (points.length === 0) {
    return (
      <div className={clsx("flex h-72 items-center justify-center rounded-lg border border-dashed border-line", className)}>
        <p className="max-w-xs text-center text-sm text-ink-muted">
          No savings data yet. Savings accumulate when JEV routes a ticket that needs human action straight to a
          queue.
        </p>
      </div>
    );
  }

  const total = data[data.length - 1].cumulative;
  const summary = `${METRIC_LABELS[metric]} chart for ${data.length} tickets, estimated total ${formatValue(metric, total)}.`;

  return (
    <div className={className}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-muted">
          Cumulative {METRIC_LABELS[metric].toLowerCase()} (estimated):{" "}
          <span className="font-mono text-sm font-semibold tabular-nums text-ink">{formatValue(metric, total)}</span>
        </p>

        <div role="group" aria-label="Savings metric" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {(["time", "cost"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={metric === option}
              onClick={() => setMetric(option)}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                metric === option ? "bg-raised text-ink" : "text-ink-subtle hover:text-ink",
              )}
            >
              {METRIC_LABELS[option]}
            </button>
          ))}
        </div>
      </div>

      <div role="img" aria-label={summary} className="h-72 w-full text-ink-muted">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={AREA_COLOR} stopOpacity={0.45} />
                <stop offset="95%" stopColor={AREA_COLOR} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="currentColor" strokeOpacity={0.15} vertical={false} />
            <XAxis
              dataKey="ticketId"
              tickFormatter={(ticketId: string) => timeByTicket.get(ticketId) ?? ticketId}
              tick={{ fill: "currentColor", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "currentColor", strokeOpacity: 0.3 }}
              interval="preserveStartEnd"
              minTickGap={28}
            />
            <YAxis
              domain={[0, "auto"]}
              tickFormatter={(value: number) => formatValue(metric, value)}
              tick={{ fill: "currentColor", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={68}
            />
            <Tooltip content={<SavingsTooltip metric={metric} />} />
            <Area
              type="monotone"
              dataKey="cumulative"
              name={`${METRIC_LABELS[metric]} (est.)`}
              stroke={AREA_COLOR}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-xs text-ink-subtle">
        {total === 0
          ? "No ticket has bypassed Gemini yet, so nothing has been saved. "
          : ""}
        Savings are estimates: each bypassed ticket is credited a fixed baseline for a Gemini draft, not a
        measurement.
      </p>
    </div>
  );
}
