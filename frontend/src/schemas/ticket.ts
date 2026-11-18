import { z } from "zod";

/* ------------------------------------------------------------------ constants */

export const TARGET_TEAMS = ["infra_team", "network_team", "hardware_team", "software_team"] as const;
export const RESOLUTION_STATUSES = ["AUTO_RESOLVED", "ASSIGNED_TO_HUMAN"] as const;
export const ENGINE_MODES = ["live", "simulated"] as const;
export const REPORT_FORMATS = ["csv", "pdf"] as const;
export const USER_ROLES = ["admin", "agent", "viewer"] as const;

// Mirrors backend schemas/ticket.py: TICKET_ID_PATTERN, EMAIL_PATTERN and the length limits.
export const TICKET_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const RAW_TEXT_MIN_LENGTH = 3;
export const RAW_TEXT_MAX_LENGTH = 5000;
export const EMAIL_MAX_LENGTH = 320;

/* ------------------------------------------------------------------ primitives */

export const targetTeamSchema = z.enum(TARGET_TEAMS);
export const resolutionStatusSchema = z.enum(RESOLUTION_STATUSES);
export const engineModeSchema = z.enum(ENGINE_MODES);
export const reportFormatSchema = z.enum(REPORT_FORMATS);
export const userRoleSchema = z.enum(USER_ROLES);

const nonNegativeInt = z.number().int().min(0);
const nonNegativeNumber = z.number().min(0);
const unitInterval = z.number().min(0).max(1);
// Pydantic serializes timezone-aware datetimes as ISO-8601 with a "Z" or numeric offset.
const isoDateTime = z.string().datetime({ offset: true });

/* ------------------------------------------------------------------ PRD §4.1 request */

export const ticketInputSchema = z
  .object({
    ticket_id: z
      .string()
      .trim()
      .regex(
        TICKET_ID_PATTERN,
        "Ticket ID must start with a letter or digit and contain only letters, digits, '-' or '_' (max 64).",
      ),
    raw_text: z
      .string()
      .trim()
      .min(RAW_TEXT_MIN_LENGTH, `Describe the issue in at least ${RAW_TEXT_MIN_LENGTH} characters.`)
      .max(RAW_TEXT_MAX_LENGTH, `Ticket text is limited to ${RAW_TEXT_MAX_LENGTH} characters.`),
    submitted_by: z
      .string()
      .trim()
      .max(EMAIL_MAX_LENGTH, `Email is limited to ${EMAIL_MAX_LENGTH} characters.`)
      .regex(EMAIL_PATTERN, "Enter a valid email address."),
  })
  .strict();

/** Fields the user types; the ticket_id is generated at submit time. */
export const ticketFormSchema = ticketInputSchema.pick({ raw_text: true, submitted_by: true });

/* ------------------------------------------------------------------ PRD §4.3 response */

export const routingInfoSchema = z.object({
  team: targetTeamSchema,
  requires_action: z.boolean(),
  jev_confidence: unitInterval,
  jev_execution_time_ms: nonNegativeInt,
});

export const resolutionInfoSchema = z.object({
  handled_by: z.string(),
  status: resolutionStatusSchema,
  response_text: z.string().nullable(),
  gemini_execution_time_ms: nonNegativeInt.nullable(),
});

/**
 * Mirrors the backend ProcessTicketResponse validator: tickets that require human action are
 * ASSIGNED_TO_HUMAN with no Gemini time; all other tickets are AUTO_RESOLVED with a Gemini time and text.
 */
export const processTicketResponseSchema = z
  .object({
    ticket_id: z.string(),
    routing: routingInfoSchema,
    resolution: resolutionInfoSchema,
  })
  .superRefine((value, ctx) => {
    const { requires_action } = value.routing;
    const { status, gemini_execution_time_ms, response_text } = value.resolution;
    const report = (path: (string | number)[], message: string): void => {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path, message });
    };

    if (requires_action) {
      if (status !== "ASSIGNED_TO_HUMAN") {
        report(["resolution", "status"], "requires_action=true must produce status ASSIGNED_TO_HUMAN");
      }
      if (gemini_execution_time_ms !== null) {
        report(
          ["resolution", "gemini_execution_time_ms"],
          "gemini_execution_time_ms must be null when Gemini is bypassed",
        );
      }
      if (!response_text) {
        report(["resolution", "response_text"], "response_text must contain the human assignment notice");
      }
    } else {
      if (status !== "AUTO_RESOLVED") {
        report(["resolution", "status"], "requires_action=false must produce status AUTO_RESOLVED");
      }
      if (gemini_execution_time_ms === null) {
        report(
          ["resolution", "gemini_execution_time_ms"],
          "gemini_execution_time_ms is required when Gemini resolves the ticket",
        );
      }
      if (!response_text) {
        report(["resolution", "response_text"], "response_text is required when Gemini resolves the ticket");
      }
    }
  });

/* ------------------------------------------------------------------ tickets and trace */

export const ticketRecordSchema = z.object({
  ticket_id: z.string(),
  raw_text: z.string(),
  submitted_by: z.string(),
  target_team: targetTeamSchema,
  requires_human_action: z.boolean(),
  confidence_score: unitInterval,
  jev_latency_ms: nonNegativeInt,
  status: resolutionStatusSchema,
  handled_by: z.string(),
  assigned_queue: z.string().nullable(),
  response_text: z.string().nullable(),
  gemini_execution_time_ms: nonNegativeInt.nullable(),
  created_at: isoDateTime,
});

export const ticketListResponseSchema = z.object({
  items: z.array(ticketRecordSchema),
  total: nonNegativeInt,
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
});

export const ticketTraceSchema = z.object({
  ticket_id: z.string(),
  jev_engine: z.string(),
  gemini_engine: z.string(),
  jev_latency_ms: nonNegativeInt,
  jev_threshold_ms: nonNegativeInt,
  jev_within_threshold: z.boolean(),
  gemini_bypassed: z.boolean(),
  gemini_execution_time_ms: nonNegativeInt.nullable(),
  decision_criteria: z.array(z.string()),
  assigned_queue: z.string().nullable(),
  time_saved_ms: nonNegativeInt,
  cost_saved_usd: nonNegativeNumber,
  rag_sources: z.array(z.string()).nullable(),
  created_at: isoDateTime,
});

/* ------------------------------------------------------------------ analytics and health */

export const analyticsSummarySchema = z.object({
  total_tickets: nonNegativeInt,
  auto_resolved_count: nonNegativeInt,
  assigned_to_human_count: nonNegativeInt,
  gemini_bypass_rate: unitInterval,
  avg_jev_latency_ms: nonNegativeNumber,
  p50_jev_latency_ms: nonNegativeNumber,
  p95_jev_latency_ms: nonNegativeNumber,
  jev_threshold_ms: nonNegativeInt,
  jev_within_threshold_rate: unitInterval,
  avg_gemini_latency_ms: nonNegativeNumber.nullable(),
  avg_confidence: unitInterval,
  total_time_saved_ms: nonNegativeInt,
  total_cost_saved_usd: nonNegativeNumber,
});

export const teamBreakdownItemSchema = z.object({
  team: targetTeamSchema,
  total: nonNegativeInt,
  auto_resolved: nonNegativeInt,
  assigned_to_human: nonNegativeInt,
  avg_jev_latency_ms: nonNegativeNumber,
});

export const latencyPointSchema = z.object({
  ticket_id: z.string(),
  created_at: isoDateTime,
  jev_latency_ms: nonNegativeInt,
  gemini_execution_time_ms: nonNegativeInt.nullable(),
  jev_within_threshold: z.boolean(),
});

export const savingsPointSchema = z.object({
  ticket_id: z.string(),
  created_at: isoDateTime,
  time_saved_ms: nonNegativeInt,
  cost_saved_usd: nonNegativeNumber,
  cumulative_time_saved_ms: nonNegativeInt,
  cumulative_cost_saved_usd: nonNegativeNumber,
});

export const analyticsResponseSchema = z.object({
  generated_at: isoDateTime,
  window_days: z.number().int().min(1).nullable(),
  summary: analyticsSummarySchema,
  team_breakdown: z.array(teamBreakdownItemSchema),
  latency_series: z.array(latencyPointSchema),
  savings_series: z.array(savingsPointSchema),
});

export const healthResponseSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  environment: z.string(),
  database_ok: z.boolean(),
  jev_engine_mode: engineModeSchema,
  gemini_engine_mode: engineModeSchema,
  rag_enabled: z.boolean(),
  jev_threshold_ms: nonNegativeInt,
});

/* ------------------------------------------------------------------ error bodies */

/** One FastAPI/Pydantic 422 validation issue. */
export const validationIssueSchema = z
  .object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
    type: z.string(),
  })
  .passthrough();

/** 401/403/404/409/503 carry a string detail, 422 carries issues, 500 also carries a request_id. */
export const apiErrorBodySchema = z
  .object({
    detail: z.union([z.string(), z.array(validationIssueSchema)]),
    request_id: z.string().optional(),
  })
  .passthrough();

/* ------------------------------------------------------------------ inferred types */

export type TargetTeam = z.infer<typeof targetTeamSchema>;
export type ResolutionStatus = z.infer<typeof resolutionStatusSchema>;
export type EngineMode = z.infer<typeof engineModeSchema>;
export type ReportFormat = z.infer<typeof reportFormatSchema>;
export type UserRole = z.infer<typeof userRoleSchema>;

export type TicketInput = z.infer<typeof ticketInputSchema>;
export type TicketFormValues = z.infer<typeof ticketFormSchema>;
export type RoutingInfo = z.infer<typeof routingInfoSchema>;
export type ResolutionInfo = z.infer<typeof resolutionInfoSchema>;
export type ProcessTicketResponse = z.infer<typeof processTicketResponseSchema>;

export type TicketRecord = z.infer<typeof ticketRecordSchema>;
export type TicketListResponse = z.infer<typeof ticketListResponseSchema>;
export type TicketTrace = z.infer<typeof ticketTraceSchema>;

export type AnalyticsSummary = z.infer<typeof analyticsSummarySchema>;
export type TeamBreakdownItem = z.infer<typeof teamBreakdownItemSchema>;
export type LatencyPoint = z.infer<typeof latencyPointSchema>;
export type SavingsPoint = z.infer<typeof savingsPointSchema>;
export type AnalyticsResponse = z.infer<typeof analyticsResponseSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;

export type ValidationIssue = z.infer<typeof validationIssueSchema>;
export type ApiErrorBody = z.infer<typeof apiErrorBodySchema>;
