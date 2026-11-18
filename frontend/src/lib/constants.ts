import type {
  AnalyticsParams,
  ListTicketsParams,
  PipelineBranch,
  PipelineNodeId,
  ResolutionStatus,
  SeededUser,
  TargetTeam,
  TicketPreset,
  UserRole,
} from "@/types/ticket";

/* ------------------------------------------------------------------ API */

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

/** Backend base URL without a trailing slash. */
export const API_BASE_URL: string = (
  configuredBaseUrl && configuredBaseUrl.length > 0 ? configuredBaseUrl : "http://localhost:8000"
).replace(/\/+$/, "");

/** Per-request timeouts. Processing allows for a live Gemini call (the backend caps it at 30 s). */
export const TIMEOUTS_MS = {
  default: 20_000,
  processTicket: 60_000,
  report: 60_000,
} as const;

export const DEFAULT_PAGE_SIZE = 20;
export const DEFAULT_SERIES_LIMIT = 50;
export const HEALTH_REFETCH_MS = 30_000;

/* ------------------------------------------------------------------ browser storage */

export const THEME_STORAGE_KEY = "ticket-engine-theme";
export const ROLE_STORAGE_KEY = "ticket-engine-role-email";

/* ------------------------------------------------------------------ users, roles, permissions */

/** Matches the PRD §4.1 sample requester. */
export const DEFAULT_SUBMITTER_EMAIL = "user@company.com";

/** The users the backend seeds on startup (backend/app/db/seed.py). */
export const SEEDED_USERS: readonly SeededUser[] = [
  { email: "agent@company.com", role: "agent", label: "Support Agent" },
  { email: "admin@company.com", role: "admin", label: "Platform Admin" },
  { email: "viewer@company.com", role: "viewer", label: "Dashboard Viewer" },
  { email: "user@company.com", role: "viewer", label: "Sample Requester" },
];

/** Agents can read everything and export reports, so the full dashboard works out of the box. */
export const DEFAULT_ROLE_EMAIL = "agent@company.com";

export type Permission = "tickets:process" | "tickets:read" | "analytics:read" | "reports:export";

/** Mirrors the backend ROLE_PERMISSIONS matrix (backend/app/services/rbac.py); the server remains the authority. */
export const ROLE_PERMISSIONS: Record<UserRole, readonly Permission[]> = {
  viewer: ["tickets:read", "analytics:read"],
  agent: ["tickets:read", "analytics:read", "tickets:process", "reports:export"],
  admin: ["tickets:read", "analytics:read", "tickets:process", "reports:export"],
};

/** True when the role grants the permission; a null role (no identity selected) grants nothing. */
export function roleHasPermission(role: UserRole | null, permission: Permission): boolean {
  return role !== null && ROLE_PERMISSIONS[role].includes(permission);
}

/* ------------------------------------------------------------------ presets (PRD §5) */

export const TICKET_PRESETS: readonly TicketPreset[] = [
  {
    id: "hardware",
    label: "Hardware Request",
    text: "Need a second 27-inch monitor and USB hub.",
    expectedTeam: "hardware_team",
    expectedRequiresAction: true,
  },
  {
    id: "network",
    label: "Network Issue",
    text: "GlobalProtect VPN failing to connect on macOS.",
    expectedTeam: "network_team",
    expectedRequiresAction: false,
  },
  {
    id: "permission",
    label: "Permission Request",
    text: "Grant IAM read access to S3 bucket prod-logs.",
    expectedTeam: "infra_team",
    expectedRequiresAction: true,
  },
  {
    id: "software",
    label: "Software How-To",
    text: "How do I export Jira board metrics to Excel?",
    expectedTeam: "software_team",
    expectedRequiresAction: false,
  },
];

/* ------------------------------------------------------------------ display labels */

export const TEAM_LABELS: Record<TargetTeam, string> = {
  infra_team: "Infrastructure",
  network_team: "Network",
  hardware_team: "Hardware",
  software_team: "Software",
};

/** Series colors for charts (Recharts needs concrete colors, not CSS variables). */
export const TEAM_COLORS: Record<TargetTeam, string> = {
  infra_team: "#8b5cf6",
  network_team: "#0ea5e9",
  hardware_team: "#f59e0b",
  software_team: "#10b981",
};

export const STATUS_LABELS: Record<ResolutionStatus, string> = {
  AUTO_RESOLVED: "Auto-resolved",
  ASSIGNED_TO_HUMAN: "Assigned to human",
};

/**
 * Backend engine strings (RoutingLog.jev_engine / gemini_engine). "simulator" is shared by JEV and Gemini.
 * The UI must label simulated results honestly, so the labels distinguish live from simulated.
 */
export const ENGINE_LABELS: Record<string, string> = {
  openrouter: "Live (TypeSafe Jev 1.14)",
  gemini: "Live (Gemini)",
  simulator: "Simulated",
  "simulator-fallback": "Simulated (live call failed)",
  bypassed: "Bypassed",
};

/** Time ranges offered on the analytics page; `value` is sent as window_days (undefined means all time). */
export const ANALYTICS_WINDOW_OPTIONS: readonly { label: string; value: number | undefined }[] = [
  { label: "All time", value: undefined },
  { label: "Last 24 hours", value: 1 },
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
];

/* ------------------------------------------------------------------ TanStack Query keys */

/** Key roots used for broad invalidation after a ticket is processed. */
export const QUERY_ROOTS = {
  tickets: ["tickets"],
  ticketTrace: ["ticket-trace"],
  analytics: ["analytics"],
} as const;

/** Keys include the acting email so cached data never crosses from one role to another. */
export const queryKeys = {
  health: ["health"] as const,
  tickets: (email: string | null, params: ListTicketsParams) => ["tickets", email, params] as const,
  ticketTrace: (email: string | null, ticketId: string) => ["ticket-trace", email, ticketId] as const,
  analytics: (email: string | null, params: AnalyticsParams) => ["analytics", email, params] as const,
};

/* ------------------------------------------------------------------ pipeline topology */

export type PipelineNodeKind = "jev" | "router" | "human" | "gemini" | "finalize";

export interface PipelineNodeDefinition {
  id: PipelineNodeId;
  label: string;
  description: string;
  kind: PipelineNodeKind;
  position: { x: number; y: number };
}

export interface PipelineEdgeDefinition {
  id: string;
  source: PipelineNodeId;
  target: PipelineNodeId;
  /** The router branch this edge belongs to; null for edges shared by both branches. */
  branch: PipelineBranch | null;
  label?: string;
}

/** Mirrors the backend LangGraph: 5 nodes (backend/app/agents/state.py NODE_* constants). */
export const PIPELINE_NODES: readonly PipelineNodeDefinition[] = [
  {
    id: "jev_classifier",
    label: "JEV Classifier",
    description: "Team, human-action flag and confidence",
    kind: "jev",
    position: { x: 0, y: 110 },
  },
  {
    id: "human_action_router",
    label: "Human-Action Router",
    description: "Single bypass decision",
    kind: "router",
    position: { x: 290, y: 110 },
  },
  {
    id: "human_dispatch",
    label: "Human Dispatch",
    description: "Assign to a human queue (Gemini bypassed)",
    kind: "human",
    position: { x: 600, y: 0 },
  },
  {
    id: "gemini_resolution",
    label: "Gemini Resolution",
    description: "RAG-grounded step-by-step answer",
    kind: "gemini",
    position: { x: 600, y: 220 },
  },
  {
    id: "finalize",
    label: "Finalize",
    description: "Build response and savings",
    kind: "finalize",
    position: { x: 900, y: 110 },
  },
];

/** Mirrors the backend WORKFLOW_EDGES: 5 edges. */
export const PIPELINE_EDGES: readonly PipelineEdgeDefinition[] = [
  { id: "e-classifier-router", source: "jev_classifier", target: "human_action_router", branch: null },
  {
    id: "e-router-human",
    source: "human_action_router",
    target: "human_dispatch",
    branch: "human",
    label: "requires_human_action = true",
  },
  {
    id: "e-router-gemini",
    source: "human_action_router",
    target: "gemini_resolution",
    branch: "gemini",
    label: "requires_human_action = false",
  },
  { id: "e-human-finalize", source: "human_dispatch", target: "finalize", branch: "human" },
  { id: "e-gemini-finalize", source: "gemini_resolution", target: "finalize", branch: "gemini" },
];

/** Nodes executed per branch, identical to the backend's `executed_nodes` for each route. */
export const PIPELINE_BRANCH_NODES: Record<PipelineBranch, readonly PipelineNodeId[]> = {
  human: ["jev_classifier", "human_action_router", "human_dispatch", "finalize"],
  gemini: ["jev_classifier", "human_action_router", "gemini_resolution", "finalize"],
};
