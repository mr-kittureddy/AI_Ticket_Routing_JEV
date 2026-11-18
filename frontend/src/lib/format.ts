/** Latency colour class: ok is under the threshold, warn is under twice the threshold, bad is above that. */
export type LatencyTone = "ok" | "warn" | "bad";

const PLACEHOLDER = "\u2013";

const numberFormat = new Intl.NumberFormat("en-US");

export function formatCount(value: number): string {
  return Number.isFinite(value) ? numberFormat.format(value) : PLACEHOLDER;
}

/** 42 -> "42 ms", 42.37 -> "42.4 ms", 1120 -> "1.12 s". */
export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return PLACEHOLDER;
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return Number.isInteger(ms) ? `${ms} ms` : `${ms.toFixed(1)} ms`;
}

/** 0.98 -> "98%" (input is a 0-1 ratio). */
export function formatPercent(ratio: number, fractionDigits = 0): string {
  if (!Number.isFinite(ratio)) return PLACEHOLDER;
  return `${(ratio * 100).toFixed(fractionDigits)}%`;
}

/** Sub-cent amounts keep four decimals (the per-ticket Gemini cost is a fraction of a cent). */
export function formatUsd(value: number): string {
  if (!Number.isFinite(value)) return PLACEHOLDER;
  const digits = value !== 0 && Math.abs(value) < 0.01 ? 4 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Formats an ISO timestamp in the viewer's locale and time zone; returns the input when it is not a date. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(date);
}

/** Time-of-day only, used for chart axes. */
export function formatTimeOfDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { timeStyle: "medium" }).format(date);
}

/** "27x faster" style contrast between a slower and a faster duration; null when it is not meaningful. */
export function formatSpeedMultiple(slowMs: number, fastMs: number): string | null {
  if (!Number.isFinite(slowMs) || !Number.isFinite(fastMs) || slowMs <= 0 || fastMs <= 0) return null;
  const ratio = slowMs / fastMs;
  if (ratio <= 1) return null;
  return ratio >= 10 ? `${Math.round(ratio)}\u00d7 faster` : `${ratio.toFixed(1)}\u00d7 faster`;
}

export function latencyTone(ms: number, thresholdMs: number): LatencyTone {
  if (ms < thresholdMs) return "ok";
  if (ms < thresholdMs * 2) return "warn";
  return "bad";
}

/**
 * Splits Gemini's numbered output ("1. ...\n2. ...") into step strings. Lines without a leading number are
 * continuation lines of the previous step. Text with no numbering yields one step per non-empty line.
 */
export function parseResolutionSteps(text: string): string[] {
  const steps: string[] = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line.length === 0) continue;
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      steps.push(numbered[2].trim());
    } else if (steps.length > 0) {
      steps[steps.length - 1] = `${steps[steps.length - 1]} ${line}`;
    } else {
      steps.push(line);
    }
  }
  return steps;
}

/** Generates a ticket id that satisfies the backend pattern, for example TCK-9F3A1C07B2D4. */
export function generateTicketId(): string {
  const bytes = new Uint8Array(6);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  const suffix = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
  return `TCK-${suffix}`;
}
