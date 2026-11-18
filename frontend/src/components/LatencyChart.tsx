import clsx from "clsx";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatMs, formatTimeOfDay } from "@/lib/format";
import type { LatencyPoint } from "@/types/ticket";

interface LatencyChartProps {
  points: LatencyPoint[];
  /** The JEV target from the backend (JEV_LATENCY_THRESHOLD_MS). */
  thresholdMs: number;
  className?: string;
}

type Scale = "log" | "linear";

// Recharts needs concrete colours. These match the --c-jev (#14b8a6) and --c-gemini (#3b82f6) design tokens.
const JEV_COLOR = "#14b8a6";
const JEV_OVER_COLOR = "#f59e0b";
const GEMINI_COLOR = "#3b82f6";
const TARGET_COLOR = "#ef4444";

interface Datum {
  ticketId: string;
  time: string;
  jev: number;
  gemini?: number;
  withinThreshold: boolean;
}

/** 1, 10, 100, ... up to a power of ten at or above the largest value (and at least 100). */
function logTicks(maxValue: number): number[] {
  const top = Math.pow(10, Math.max(2, Math.ceil(Math.log10(Math.max(1, maxValue)))));
  const ticks: number[] = [];
  for (let value = 1; value <= top; value *= 10) ticks.push(value);
  return ticks;
}

interface LatencyTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: Datum }>;
  thresholdMs: number;
}

function LatencyTooltip({ active, payload, thresholdMs }: LatencyTooltipProps): JSX.Element | null {
  const datum = payload?.[0]?.payload;
  if (!active || datum === undefined) return null;

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-card">
      <p className="font-mono font-semibold text-ink">{datum.ticketId}</p>
      <p className="text-ink-subtle">{datum.time}</p>
      <dl className="mt-1.5 space-y-0.5">
        <div className="flex justify-between gap-6">
          <dt className="text-ink-muted">JEV</dt>
          <dd className="font-mono tabular-nums text-ink">{formatMs(datum.jev)}</dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt className="text-ink-muted">Gemini</dt>
          <dd className="font-mono tabular-nums text-ink">
            {datum.gemini !== undefined ? formatMs(datum.gemini) : "Bypassed"}
          </dd>
        </div>
      </dl>
      <p className={clsx("mt-1.5 font-medium", datum.withinThreshold ? "text-ok" : "text-warn")}>
        {datum.withinThreshold ? `Under the ${thresholdMs} ms target` : `Over the ${thresholdMs} ms target`}
      </p>
    </div>
  );
}

export function LatencyChart({ points, thresholdMs, className }: LatencyChartProps): JSX.Element {
  const [scale, setScale] = useState<Scale>("log");

  const data = useMemo<Datum[]>(
    () =>
      points.map((point) => ({
        ticketId: point.ticket_id,
        time: formatTimeOfDay(point.created_at),
        jev: point.jev_latency_ms,
        gemini: point.gemini_execution_time_ms ?? undefined,
        withinThreshold: point.jev_within_threshold,
      })),
    [points],
  );

  const timeByTicket = useMemo(() => new Map(data.map((datum) => [datum.ticketId, datum.time])), [data]);

  const maxValue = useMemo(
    () => data.reduce((max, datum) => Math.max(max, datum.jev, datum.gemini ?? 0), Math.max(thresholdMs, 1)),
    [data, thresholdMs],
  );
  const ticks = useMemo(() => logTicks(maxValue), [maxValue]);

  if (data.length === 0) {
    return (
      <div className={clsx("flex h-72 items-center justify-center rounded-lg border border-dashed border-line", className)}>
        <p className="max-w-xs text-center text-sm text-ink-muted">
          No latency data yet. Submit a ticket from the dashboard to see JEV and Gemini timings here.
        </p>
      </div>
    );
  }

  const withinCount = data.filter((datum) => datum.withinThreshold).length;
  const summary = `Latency chart for ${data.length} tickets. JEV was under the ${thresholdMs} millisecond target on ${withinCount} of them.`;

  return (
    <div className={className}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: JEV_COLOR }} />
            JEV (under target)
          </li>
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: JEV_OVER_COLOR }} />
            JEV (over target)
          </li>
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: GEMINI_COLOR }} />
            Gemini
          </li>
        </ul>

        <div role="group" aria-label="Chart scale" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {(["log", "linear"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={scale === option}
              onClick={() => setScale(option)}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                scale === option ? "bg-raised text-ink" : "text-ink-subtle hover:text-ink",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div role="img" aria-label={summary} className="h-72 w-full text-ink-muted">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }} barGap={2}>
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
            {scale === "log" ? (
              <YAxis
                scale="log"
                domain={[1, ticks[ticks.length - 1]]}
                ticks={ticks}
                allowDataOverflow
                tickFormatter={(value: number) => formatMs(value)}
                tick={{ fill: "currentColor", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={58}
              />
            ) : (
              <YAxis
                domain={[0, "auto"]}
                tickFormatter={(value: number) => formatMs(value)}
                tick={{ fill: "currentColor", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={58}
              />
            )}
            <Tooltip
              cursor={{ fill: "currentColor", fillOpacity: 0.06 }}
              content={<LatencyTooltip thresholdMs={thresholdMs} />}
            />
            {thresholdMs > 0 && (
              <ReferenceLine
                y={thresholdMs}
                stroke={TARGET_COLOR}
                strokeDasharray="5 4"
                label={{ value: `${thresholdMs} ms target`, position: "insideTopRight", fill: "currentColor", fontSize: 11 }}
              />
            )}
            <Bar dataKey="jev" name="JEV" radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false}>
              {data.map((datum) => (
                <Cell key={datum.ticketId} fill={datum.withinThreshold ? JEV_COLOR : JEV_OVER_COLOR} />
              ))}
            </Bar>
            <Bar
              dataKey="gemini"
              name="Gemini"
              fill={GEMINI_COLOR}
              radius={[3, 3, 0, 0]}
              maxBarSize={22}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-xs text-ink-subtle">
        {scale === "log"
          ? "Log scale: each gridline is ten times the one below, so millisecond JEV bars and second-long Gemini bars stay readable together."
          : "Linear scale: JEV bars can look tiny next to Gemini because the two differ by orders of magnitude."}{" "}
        Tickets routed to a human have no Gemini bar because Gemini was bypassed.
      </p>
    </div>
  );
}
