import type {
  ReportFormat,
  ResolutionStatus,
  TargetTeam,
  TicketInput,
  TicketTrace,
  ProcessTicketResponse,
  UserRole,
} from "@/schemas/ticket";

export type {
  AnalyticsResponse,
  AnalyticsSummary,
  ApiErrorBody,
  EngineMode,
  HealthResponse,
  LatencyPoint,
  ProcessTicketResponse,
  ReportFormat,
  ResolutionInfo,
  ResolutionStatus,
  RoutingInfo,
  SavingsPoint,
  TargetTeam,
  TeamBreakdownItem,
  TicketFormValues,
  TicketInput,
  TicketListResponse,
  TicketRecord,
  TicketTrace,
  UserRole,
  ValidationIssue,
} from "@/schemas/ticket";

/** Query parameters for GET /api/tickets (sent as page, page_size, team, status, requires_human_action, search). */
export interface ListTicketsParams {
  page?: number;
  pageSize?: number;
  team?: TargetTeam;
  status?: ResolutionStatus;
  requiresHumanAction?: boolean;
  search?: string;
}

/** Query parameters for GET /api/analytics (sent as window_days, series_limit). */
export interface AnalyticsParams {
  windowDays?: number;
  seriesLimit?: number;
}

/** Query parameters for GET /api/reports (sent as format, window_days). */
export interface ReportParams {
  format: ReportFormat;
  windowDays?: number;
}

/** A report file received from GET /api/reports. */
export interface DownloadedReport {
  blob: Blob;
  filename: string;
}

/** One of the pre-loaded sample scenarios in the ingestion panel (PRD §5). */
export interface TicketPreset {
  id: string;
  label: string;
  text: string;
  expectedTeam: TargetTeam;
  expectedRequiresAction: boolean;
}

/** A seeded backend user the dashboard can act as via the X-User-Email header. */
export interface SeededUser {
  email: string;
  role: UserRole;
  label: string;
}

/** Everything the dashboard panels need after one submission. */
export interface ProcessedTicket {
  request: TicketInput;
  response: ProcessTicketResponse;
  /** Null when the trace could not be loaded (for example, the caller lacks tickets:read). */
  trace: TicketTrace | null;
  /** Browser-measured time from sending the request to receiving the response. */
  clientRoundTripMs: number;
  completedAt: string;
}

/** Node ids of the LangGraph pipeline, identical to the backend's NODE_* constants. */
export type PipelineNodeId =
  | "jev_classifier"
  | "human_action_router"
  | "human_dispatch"
  | "gemini_resolution"
  | "finalize";

/** Which branch the human-action router chose. */
export type PipelineBranch = "human" | "gemini";
