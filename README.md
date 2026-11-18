# IT Support Ticket AI Routing & Resolution Engine

A single-page prototype that classifies raw IT support tickets, routes them to the right team, and either assigns
them to a human queue or drafts a step-by-step resolution.

- **JEV** (TypeSafe Jev 1.14 via OpenRouter `/v1/systemone`, `typesafe/jev-1.14`) uses typed `choice` and `noul` primitives to pick the team, decide whether human action is required (purchase, physical install, or admin privilege), and report calibrated probabilities in under 100 ms.
- **Tickets that need human action bypass Gemini** and go straight to a human queue.
- **All other tickets** get a numbered resolution drafted by **Gemini** (`gemini-2.5-flash`), grounded by similar
  past tickets from a ChromaDB knowledge base.

## What has and has not been verified

Checked in the environment where this code was generated (Python 3.12, Node 20):

| Check | Result |
|---|---|
| `cd backend && pytest -q` | 127 tests pass |
| `alembic upgrade head` on a fresh SQLite file | applies cleanly |
| Real `uvicorn` server, then `curl` | health, both routing branches, analytics all return correct data; ChromaDB knowledge base initialises |
| `cd frontend && npx tsc --noEmit` | no type errors |
| `cd frontend && npx vite build` | production bundle builds |

**Not verified** (no browser, Docker daemon or API keys were available):

- The dashboard has never been rendered or clicked through in a browser. Layout, the React Flow diagram, the charts
  (especially the log-scale axis) and both themes are untested visually.
- `docker compose up --build` has never been run. The Dockerfiles and Compose file were written but not built.
- Live OpenRouter and Gemini calls have never been made. Their request and response handling follows the documented
  APIs, and any failure falls back to the simulator (labelled on screen), but it is unproven against the real services.
- PostgreSQL has never been used. The schema and migration were only run on SQLite.
- Python 3.11 (the Docker image's version) was not tested; the suite ran on 3.12.
- The frontend has no automated tests.

## Contents

1. [How a ticket flows](#how-a-ticket-flows)
2. [Quick start with Docker](#quick-start-with-docker)
3. [Running locally](#running-locally)
4. [Configuration](#configuration)
5. [Simulator mode vs live engines](#simulator-mode-vs-live-engines)
6. [API, roles and permissions](#api-roles-and-permissions)
7. [PRD contracts](#prd-contracts)
8. [Design decisions](#design-decisions)
9. [Project layout](#project-layout)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)
12. [Security notes](#security-notes)
13. [Known limitations](#known-limitations)

## How a ticket flows

```
POST /api/process-ticket
        |
        v
 jev_classifier  ->  human_action_router
                          |
        requires_human_action = true  --->  human_dispatch   (Gemini bypassed, savings recorded)
        requires_human_action = false --->  gemini_resolution (RAG lookup, then Gemini)
                          |
                          v
                       finalize  ->  PRD response  ->  stored in the database with an audit entry
```

The graph is a LangGraph `StateGraph`. The bypass decision is made in exactly one place, the router node, and the
response schema independently rejects any result that breaks the rule (for example, a human-assigned ticket that
carries a Gemini time). The dashboard draws the same five-node graph and highlights the path the latest ticket took.

## Quick start with Docker

Requires Docker with the Compose plugin.

```bash
cp .env.example .env        # every value is optional; the defaults run the full stack in simulator mode
docker compose up --build
```

| What | Where |
|---|---|
| Dashboard | http://localhost:5173 |
| API health | http://localhost:8000/api/health |

The dashboard is served on host port **5173** on purpose: the backend only allows CORS from
`http://localhost:5173` and `http://127.0.0.1:5173`. If you change the port, update `CORS_ORIGINS` in
`docker-compose.yml` to match, and rebuild.

In Docker the backend runs `alembic upgrade head` against PostgreSQL before starting, with `DEBUG=false`, so the
interactive docs (`/docs`) are disabled. The frontend image runs `npm run build`, which includes the TypeScript
check, so a type error fails the build. Stop with `docker compose down`; add `-v` to also delete the database and
knowledge-base volumes.

## Running locally

Requires Python 3.11+ and Node 18.18+.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; the defaults work
```

Then choose **one** way to create the database tables:

**Option A: Alembic (supported, and required for PostgreSQL)**

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Option B: automatic creation (SQLite only)**

```bash
uvicorn app.main:app --reload --port 8000
```

If the tables are missing and the database is a local SQLite file, the app creates them itself.

> **Do not mix the two on the same SQLite file.** If the app auto-created the tables and you later run
> `alembic upgrade head`, the initial migration fails with "table already exists". To switch, delete the
> `.db` file first. Docker is not affected, because Alembic always runs first against an empty database.

On startup the app seeds 8 routing rules and 4 users (idempotent) and opens the ChromaDB knowledge base.
With `DEBUG=true` (the default locally), interactive API docs are at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env               # optional; VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev                        # http://localhost:5173
```

The dev server uses a fixed port (`strictPort`), so if 5173 is taken it fails instead of moving to another port
that the backend's CORS list would reject. A `package-lock.json` is included, so `npm ci` also works.

### Try the four preset scenarios

| Preset | Team | Human action | Result |
|---|---|---|---|
| Hardware Request: "Need a second 27-inch monitor and USB hub." | `hardware_team` | Yes | Hardware Procurement Queue, Gemini skipped |
| Network Issue: "GlobalProtect VPN failing to connect on macOS." | `network_team` | No | Gemini-drafted steps |
| Permission Request: "Grant IAM read access to S3 bucket prod-logs." | `infra_team` | Yes | Infrastructure Access Queue, Gemini skipped |
| Software How-To: "How do I export Jira board metrics to Excel?" | `software_team` | No | Gemini-drafted steps |

## Configuration

Environment variables, read from the process environment or from `.env` in the directory the backend starts in.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | masked placeholder | JEV live mode. Must start with `sk-or`; anything else means simulator mode. |
| `GEMINI_API_KEY` | masked placeholder | Gemini live mode. Must start with `AIza`; anything else means simulator mode. |
| `OPENROUTER_MODEL` | `typesafe/jev-1.14` | TypeSafe Jev 1.14 System One decision model called via OpenRouter. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model that drafts resolutions. |
| `JEV_LATENCY_THRESHOLD_MS` | `500` | JEV speed target used for the badges and statistics. |
| `DATABASE_URL` | `sqlite:///./support_tickets.db` | SQLAlchemy URL. Use `postgresql+psycopg2://...` for PostgreSQL. |
| `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION` | `./chroma_store` / `past_tickets_kb` | Knowledge-base storage. |
| `RAG_TOP_K` | `3` | Similar past tickets used to ground Gemini. |
| `CORS_ORIGINS` | the two `:5173` origins | **JSON list**, for example `["http://localhost:5173"]`. |
| `ENFORCE_RBAC_ON_PROCESS_TICKET` | `false` | When `true`, submitting a ticket requires an agent or admin identity. |
| `OPENROUTER_TIMEOUT_SECONDS` / `GEMINI_TIMEOUT_SECONDS` | `5` / `30` | Outbound call timeouts. |
| `BASELINE_GEMINI_LATENCY_MS` | `1500` | Time credited as saved per ticket that bypasses Gemini. |
| `BASELINE_GEMINI_COST_USD` | `0.0004` | Cost credited as saved per ticket that bypasses Gemini. |
| `ENVIRONMENT` / `DEBUG` | `development` / `true` | `development` gives readable logs, anything else gives JSON logs. `DEBUG=false` disables `/docs`. |

Frontend: `VITE_API_BASE_URL` (default `http://localhost:8000`) is the URL the **browser** uses to reach the
backend. Vite bakes it in at build time.

**The savings figures are assumptions, not measurements.** The PRD only says Gemini takes roughly 1000 to
2000 ms. The 1500 ms and $0.0004 baselines are placeholders: adjust them to your real numbers. The interface
labels every savings figure as an estimate.

## Simulator mode vs live engines

With blank or masked API keys the app runs without any external service:

- **JEV** uses a deterministic keyword-evidence rule engine seeded from 8 routing rules. It reproduces the four PRD
  presets exactly, and its time (a few milliseconds at most) is real compute time for the local rules.
- **Gemini** uses a template drafter that waits a repeatable 1000 to 2000 ms so the latency contrast stays
  realistic. That wait is deliberate and is labelled as simulated.

The dashboard states which mode produced each result: header badges come from `/api/health`, and per-ticket badges
come from the routing trace.

| Badge | Meaning |
|---|---|
| Live (OpenRouter) / Live (Gemini) | A real call succeeded. |
| Simulated | Keys are masked or missing; the deterministic engine ran. |
| Simulated (live call failed) | A live call was attempted and failed, so the simulator answered instead. |
| Bypassed | Gemini was skipped because the ticket needs human action. |

In live mode, the "<500 ms" badge is computed from the **measured** time, never hardcoded. A live OpenRouter call
includes the network round trip and may well exceed 500 ms. The interface says so rather than claiming the target
was met.

## API, roles and permissions

| Method and path | Permission | Notes |
|---|---|---|
| `POST /api/process-ticket` | none by default | The PRD endpoint. Requires `tickets:process` only when `ENFORCE_RBAC_ON_PROCESS_TICKET=true`. |
| `GET /api/tickets` | `tickets:read` | Paginated history. Filters: `page`, `page_size`, `team`, `status`, `requires_human_action`, `search`. |
| `GET /api/tickets/{ticket_id}/trace` | `tickets:read` | Decision criteria, engine modes, threshold result and estimated savings. |
| `GET /api/analytics` | `analytics:read` | Latency, bypass rate and savings. Optional `window_days`, `series_limit`. |
| `GET /api/reports?format=csv\|pdf` | `reports:export` | File download. Optional `window_days`. |
| `GET /api/health` | none | Database status and whether each engine is live or simulated. |

Callers identify themselves with an `X-User-Email` header. The seeded users are:

| Email | Role | Can |
|---|---|---|
| `viewer@company.com`, `user@company.com` | viewer | read tickets and analytics |
| `agent@company.com` | agent | viewer permissions, process tickets, export reports |
| `admin@company.com` | admin | everything (currently the same set as agent) |

The dashboard has a role selector in the header (it starts as the agent) so you can try each role. Errors use
`{"detail": ...}`: 401 (unknown or missing user), 403 (lacking permission), 404, 409 (duplicate `ticket_id`),
422 (validation, a list of issues), 503 (database unavailable) and 500 (`detail` plus a `request_id`). Every
response carries an `X-Request-ID` header, which is also stored on each audit row.

## PRD contracts

`POST /api/process-ticket` request (PRD 4.1):

```json
{ "ticket_id": "TCK-8821", "raw_text": "My GlobalProtect VPN keeps dropping...", "submitted_by": "user@company.com" }
```

Response (PRD 4.3):

```json
{
  "ticket_id": "TCK-8821",
  "routing": { "team": "network_team", "requires_action": false, "jev_confidence": 0.98, "jev_execution_time_ms": 42 },
  "resolution": {
    "handled_by": "Gemini 2.5 Flash",
    "status": "AUTO_RESOLVED",
    "response_text": "1. Open GlobalProtect Settings...\n2. Clear DNS Cache...",
    "gemini_execution_time_ms": 1120
  }
}
```

For a ticket that needs human action: `status` is `ASSIGNED_TO_HUMAN`, `handled_by` is "Human Representative",
`response_text` starts with "Assigned to <Queue>.", and `gemini_execution_time_ms` is `null`.

The internal JEV decision (PRD 4.2: `target_team`, `requires_human_action`, `confidence_score`, `jev_latency_ms`)
is persisted and shown on the dashboard. The PRD response has no field for the decision criteria or the savings, so
those come from the separate, additive trace endpoint rather than by altering the contract.

## Design decisions

The master prompt and the PRD disagree in places. The PRD's contracts were kept exactly, and the conflicts were
resolved as follows:

| # | Conflict | Resolution |
|---|---|---|
| C1 | Prompt: PostgreSQL, Alembic, ChromaDB. PRD: in-memory or SQLite. | SQLAlchemy and Alembic, SQLite by default, PostgreSQL through `DATABASE_URL` (used in Docker). ChromaDB is optional grounding that never changes a contract. |
| C2 | Prompt: extra endpoints, RBAC, audit. PRD: one endpoint, no auth. | `/api/process-ticket` is implemented exactly and stays open by default. The other endpoints are read-only additions, RBAC is a role header, and audit logging is on. |
| C3 | Prompt: multi-page app. PRD: one page. | One dashboard page at `/`, plus a secondary `/analytics` view. |
| C4 | Two field-name sets (`jev_latency_ms` vs `jev_execution_time_ms`). | Both kept verbatim: 4.2 for the internal decision, 4.3 for the API response. They are different schemas. |
| C5 | "JEV SDK/API" vs the provided `config.py` (OpenRouter). | `config.py` is used verbatim and extended by `settings.py` without editing it. A deterministic simulator reproduces the four presets when keys are masked. |
| C6 | Prompt lists three nodes. | The graph also has a human-action router node, which is the single bypass decision point. |
| C7 | PRD says three panels but numbers four. | Four panels, laid out as in the wireframe. |

Choices made beyond either document: the extended `settings.py`, the savings baselines (assumptions, see above),
the human queue names (Hardware Procurement, Infrastructure Access, Software License, Network Change Request),
and CSV and PDF reports.

## Project layout

```
backend/
  app/
    main.py                 FastAPI app, lifespan, request IDs, CORS
    core/                   config.py (provided), settings.py, logging.py, timeutil.py
    db/                     base, session, models, seed
    schemas/                ticket.py (PRD contracts), analytics.py
    services/               jev, gemini, rag, rbac, audit, tickets, analytics, reports
    agents/                 state.py, nodes.py, ticket_workflow.py (LangGraph)
    api/                    routes_process, routes_tickets, routes_analytics, routes_reports, routes_health
  alembic/                  env.py, script.py.mako, versions/0001_initial.py
  tests/                    conftest, schemas, JEV, workflow, API
frontend/
  src/
    schemas/ types/ lib/    Zod contracts, types, constants, formatters
    services/api.ts         typed client with timeouts and normalized errors
    context/ hooks/         theme and role, TanStack Query hooks
    components/             badges, charts, pipeline diagram, history table, ...
    panels/                 the four PRD panels
    pages/                  Dashboard, AnalyticsPage
docker-compose.yml          db, backend, frontend
```

## Testing

```bash
cd backend && pytest -q            # run from backend/; uses masked keys and a temporary database
cd frontend && npm run typecheck   # strict TypeScript
```

The backend suite covers the PRD schemas (including the bypass rule), the four presets through the JEV service and
the full workflow (asserting Gemini and RAG never run for human-action tickets), and the HTTP surface: status codes,
RBAC, pagination and filters, trace, analytics totals, CSV and PDF export (including formula neutralization), audit
rows, request IDs, CORS and the generic 500 handler. There are no automated frontend tests.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Browser shows a CORS error, or "Cannot reach the API" | The page must be served from `http://localhost:5173` or `http://127.0.0.1:5173`, or its origin must be in `CORS_ORIGINS`. Also check `VITE_API_BASE_URL` points at a running backend. |
| Backend fails at startup parsing `CORS_ORIGINS` | It must be a JSON list: `["http://localhost:5173"]`. |
| `table ... already exists` during `alembic upgrade head` | The app auto-created the SQLite tables earlier. Delete the `.db` file, or skip Alembic. |
| Backend says tables are missing on PostgreSQL | Run `alembic upgrade head` first; auto-creation is SQLite only. |
| `ModuleNotFoundError: app` | Run commands from `backend/`. |
| Port 5173 or 8000 is busy | Stop the other process. The frontend port is fixed because of CORS. |
| Postgres connection errors in Docker | The password sits inside `DATABASE_URL`, so use letters and digits only. After changing credentials, `docker compose down -v` to drop the old volume. |
| Live keys set but badges say "Simulated" | A key is only treated as real if it starts with `sk-or` (OpenRouter) or `AIza` (Gemini). |
| "Simulated (live call failed)" | The live call errored or timed out and the simulator answered. Check the key, the model name and network access. The criteria list on the ticket's trace names the error type. |
| ChromaDB or `onnxruntime` fails to install | Use a glibc-based Python image or a supported platform (not Alpine). The app still runs without the knowledge base, and the header badge shows it as Off. |
| Frontend Docker build fails | The image runs `npm run build`, which type-checks first. Run `npm run typecheck` locally to see the error. |

## Security notes

- **Identity is not verified.** The `X-User-Email` header is trusted as sent, so anyone who knows a seeded email can
  act as that user. The PRD asks for no authentication, so this is acceptable for a prototype and the role selector
  is a demo convenience, not a security boundary. A real deployment must replace it with verified tokens (OIDC or
  JWT) and enable `ENFORCE_RBAC_ON_PROCESS_TICKET`.
- API keys stay on the backend and are never sent to the browser. Log and audit entries redact secret-like keys, and
  audit rows never store ticket text.
- CORS is limited to the dashboard origins. CSV exports prefix cells that start with `=`, `+`, `-` or `@`, which
  blocks spreadsheet formula injection.
- Change the default Postgres password for anything other than local use.

## Known limitations

- See [What has and has not been verified](#what-has-and-has-not-been-verified) for what has never been run.
- The knowledge base uses a small local hashing embedding, so similarity is lexical rather than semantic. It keeps
  setup free of model downloads but retrieves less cleverly than a learned embedding.
- Dependencies in `requirements.txt` only have lower bounds, so a future major release of LangGraph, LangChain,
  ChromaDB or similar could change an API. Pin them (`pip freeze`) once you have a working environment.
- Analytics aggregate the newest 50,000 routing logs in Python for SQLite and PostgreSQL portability.
- Savings figures are estimates from fixed baselines, not measurements.
