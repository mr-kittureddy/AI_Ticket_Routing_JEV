import type { z } from "zod";
import { API_BASE_URL, TIMEOUTS_MS } from "@/lib/constants";
import {
  analyticsResponseSchema,
  apiErrorBodySchema,
  healthResponseSchema,
  processTicketResponseSchema,
  ticketInputSchema,
  ticketListResponseSchema,
  ticketTraceSchema,
} from "@/schemas/ticket";
import type {
  AnalyticsParams,
  AnalyticsResponse,
  DownloadedReport,
  HealthResponse,
  ListTicketsParams,
  ProcessTicketResponse,
  ReportParams,
  TicketInput,
  TicketListResponse,
  TicketTrace,
  ValidationIssue,
} from "@/types/ticket";

/* ------------------------------------------------------------------ errors */

export type ApiErrorKind = "network" | "timeout" | "http" | "validation" | "contract";

interface ApiErrorInit {
  kind: ApiErrorKind;
  message: string;
  status?: number | null;
  requestId?: string | null;
  issues?: ValidationIssue[];
}

/** Every failure the client can produce. The message is safe to show to the user. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly requestId: string | null;
  readonly issues: ValidationIssue[];

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.requestId = init.requestId ?? null;
    this.issues = init.issues ?? [];
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** The ticket_id has already been processed. */
  get isConflict(): boolean {
    return this.status === 409;
  }

  /** Transient failures worth retrying. */
  get isRetryable(): boolean {
    return (
      this.kind === "network" ||
      this.kind === "timeout" ||
      this.status === 502 ||
      this.status === 503 ||
      this.status === 504
    );
  }

  /** First message per body field from a 422 (or client-side validation) response, keyed by field name. */
  fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const issue of this.issues) {
      const field = issue.loc.slice(1).find((part): part is string => typeof part === "string");
      if (field !== undefined && !(field in result)) {
        result[field] = issue.msg;
      }
    }
    return result;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message.length > 0) return error.message;
  return "Something went wrong. Please try again.";
}

export function getErrorRequestId(error: unknown): string | null {
  return error instanceof ApiError ? error.requestId : null;
}

const STATUS_MESSAGES: Record<number, string> = {
  400: "The request was not accepted.",
  401: "A known user is required. Pick a user from the role selector.",
  403: "Your current role does not have permission for this action.",
  404: "The requested item was not found.",
  409: "This ticket ID has already been processed.",
  422: "The request was rejected because some values are invalid.",
  500: "The server hit an unexpected error.",
  502: "The server is temporarily unreachable. Please retry.",
  503: "The service is temporarily unavailable. Please retry.",
  504: "The server took too long to respond. Please retry.",
};

function describeHttpFailure(status: number, detail: string | null, issues: ValidationIssue[]): string {
  if (issues.length > 0) {
    const first = issues[0];
    const field = first.loc.slice(1).join(".");
    return field.length > 0 ? `${field}: ${first.msg}` : first.msg;
  }
  if (status === 401) return STATUS_MESSAGES[401];
  if (detail !== null && detail.length > 0 && status !== 500) return detail;
  return STATUS_MESSAGES[status] ?? `The request failed with status ${status}.`;
}

async function toHttpError(response: Response): Promise<ApiError> {
  const headerRequestId = response.headers.get("X-Request-ID");
  let detail: string | null = null;
  let issues: ValidationIssue[] = [];
  let bodyRequestId: string | null = null;

  try {
    const parsed = apiErrorBodySchema.safeParse(await response.json());
    if (parsed.success) {
      if (typeof parsed.data.detail === "string") {
        detail = parsed.data.detail;
      } else {
        issues = parsed.data.detail;
      }
      bodyRequestId = parsed.data.request_id ?? null;
    }
  } catch {
    // The error body was not JSON; the status code alone drives the message.
  }

  return new ApiError({
    kind: "http",
    status: response.status,
    message: describeHttpFailure(response.status, detail, issues),
    requestId: bodyRequestId ?? headerRequestId,
    issues,
  });
}

/* ------------------------------------------------------------------ transport */

/** Options every endpoint function accepts. */
export interface RequestOptions {
  /** Sent as X-User-Email; omit for an anonymous call. */
  userEmail?: string | null;
  /** Lets TanStack Query cancel in-flight requests. */
  signal?: AbortSignal;
}

type QueryValue = string | number | boolean | null | undefined;

interface RequestConfig {
  method: "GET" | "POST";
  path: string;
  query?: Record<string, QueryValue>;
  body?: unknown;
  userEmail?: string | null;
  signal?: AbortSignal;
  timeoutMs: number;
  accept: string;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const queryString = params.toString();
  return `${API_BASE_URL}${path}${queryString.length > 0 ? `?${queryString}` : ""}`;
}

/** fetch with a hard timeout. Caller cancellation is rethrown untouched so TanStack Query can ignore it. */
async function send(url: string, init: RequestInit, timeoutMs: number, external?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = (): void => controller.abort();

  if (external) {
    if (external.aborted) {
      controller.abort();
    } else {
      external.addEventListener("abort", onExternalAbort, { once: true });
    }
  }

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) {
      throw new ApiError({
        kind: "timeout",
        message: `The request timed out after ${Math.round(timeoutMs / 1000)} seconds.`,
      });
    }
    if (external?.aborted) {
      throw error;
    }
    throw new ApiError({
      kind: "network",
      message: `Cannot reach the API at ${API_BASE_URL}. Make sure the backend is running and that its CORS settings allow this page.`,
    });
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", onExternalAbort);
  }
}

async function execute(config: RequestConfig): Promise<Response> {
  const headers: Record<string, string> = { Accept: config.accept };
  if (config.body !== undefined) headers["Content-Type"] = "application/json";
  if (config.userEmail) headers["X-User-Email"] = config.userEmail;

  const response = await send(
    buildUrl(config.path, config.query),
    {
      method: config.method,
      headers,
      body: config.body !== undefined ? JSON.stringify(config.body) : undefined,
      cache: "no-store",
    },
    config.timeoutMs,
    config.signal,
  );

  if (!response.ok) {
    throw await toHttpError(response);
  }
  return response;
}

function contractError(path: string, response: Response, issues?: unknown): ApiError {
  if (import.meta.env.DEV) {
    console.error(`[api] ${path} returned a body that does not match the expected contract`, issues);
  }
  return new ApiError({
    kind: "contract",
    status: response.status,
    requestId: response.headers.get("X-Request-ID"),
    message: "The server response did not match the expected format. The frontend and backend versions may differ.",
  });
}

async function requestJson<S extends z.ZodTypeAny>(
  schema: S,
  config: Omit<RequestConfig, "accept">,
): Promise<z.output<S>> {
  const response = await execute({ ...config, accept: "application/json" });

  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error) {
    throw contractError(config.path, response, error);
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw contractError(config.path, response, parsed.error.issues);
  }
  return parsed.data;
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  if (!match) return fallback;
  let name = match[1];
  try {
    name = decodeURIComponent(name);
  } catch {
    // Keep the raw value when it is not percent-encoded.
  }
  const safe = name.replace(/[\\/]/g, "_").trim();
  return safe.length > 0 ? safe : fallback;
}

/* ------------------------------------------------------------------ endpoints */

/** POST /api/process-ticket (PRD §4.1 request, §4.3 response). Input is validated before it is sent. */
export async function processTicket(
  input: TicketInput,
  options: RequestOptions = {},
): Promise<ProcessTicketResponse> {
  const parsed = ticketInputSchema.safeParse(input);
  if (!parsed.success) {
    const issues: ValidationIssue[] = parsed.error.issues.map((issue) => ({
      loc: ["body", ...issue.path],
      msg: issue.message,
      type: issue.code,
    }));
    throw new ApiError({
      kind: "validation",
      message: parsed.error.issues[0]?.message ?? "The ticket is not valid.",
      issues,
    });
  }

  return requestJson(processTicketResponseSchema, {
    method: "POST",
    path: "/api/process-ticket",
    body: parsed.data,
    userEmail: options.userEmail,
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.processTicket,
  });
}

/** GET /api/tickets. The status filter is sent as `status`, exactly as the backend declares it. */
export function listTickets(params: ListTicketsParams = {}, options: RequestOptions = {}): Promise<TicketListResponse> {
  const search = params.search?.trim();
  return requestJson(ticketListResponseSchema, {
    method: "GET",
    path: "/api/tickets",
    query: {
      page: params.page,
      page_size: params.pageSize,
      team: params.team,
      status: params.status,
      requires_human_action: params.requiresHumanAction,
      search: search && search.length > 0 ? search : undefined,
    },
    userEmail: options.userEmail,
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.default,
  });
}

/** GET /api/tickets/{ticket_id}/trace. */
export function getTicketTrace(ticketId: string, options: RequestOptions = {}): Promise<TicketTrace> {
  return requestJson(ticketTraceSchema, {
    method: "GET",
    path: `/api/tickets/${encodeURIComponent(ticketId)}/trace`,
    userEmail: options.userEmail,
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.default,
  });
}

/** GET /api/analytics. */
export function getAnalytics(params: AnalyticsParams = {}, options: RequestOptions = {}): Promise<AnalyticsResponse> {
  return requestJson(analyticsResponseSchema, {
    method: "GET",
    path: "/api/analytics",
    query: { window_days: params.windowDays, series_limit: params.seriesLimit },
    userEmail: options.userEmail,
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.default,
  });
}

/** GET /api/health (no authentication). */
export function getHealth(options: RequestOptions = {}): Promise<HealthResponse> {
  return requestJson(healthResponseSchema, {
    method: "GET",
    path: "/api/health",
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.default,
  });
}

/** GET /api/reports. Returns the file and its server-provided filename; the caller triggers the browser download. */
export async function downloadReport(params: ReportParams, options: RequestOptions = {}): Promise<DownloadedReport> {
  const response = await execute({
    method: "GET",
    path: "/api/reports",
    query: { format: params.format, window_days: params.windowDays },
    userEmail: options.userEmail,
    signal: options.signal,
    timeoutMs: TIMEOUTS_MS.report,
    accept: params.format === "pdf" ? "application/pdf" : "text/csv",
  });

  const blob = await response.blob();
  const filename = filenameFromDisposition(
    response.headers.get("Content-Disposition"),
    `ticket-routing-report.${params.format}`,
  );
  return { blob, filename };
}
