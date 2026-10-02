# FlowForge

FlowForge is a multi-tenant SaaS platform for designing, publishing, executing, monitoring, approving, and auditing internal business workflows.

This repository contains **M0 bootstrap, M1 authentication, and M2 organizations**: a Next.js frontend, FastAPI API, PostgreSQL-backed sessions, tenant-scoped organizations/memberships/invitations, local infrastructure, migrations, and automated checks. Later business features remain separate milestones. The files in `/docs` remain the source of truth for architecture, scope, engineering constraints, and implementation planning.

## Product idea

A company can define a workflow such as:

```text
Manual Trigger
  -> Manager Approval
  -> Condition: amount > 5000
  -> Finance Approval
  -> Email
  -> Accounting Webhook
  -> End
```

FlowForge must support long-running workflows, human approvals, reliable asynchronous execution, retries, audit history, realtime updates, multi-tenant isolation, and production-style observability.

## Initial technical direction

- Frontend: Next.js App Router + React + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL
- Cache/realtime support: Redis
- Background jobs: Celery
- Broker: RabbitMQ
- Files: S3-compatible object storage
- Realtime: WebSockets
- Architecture: Modular monolith first, with clear extraction boundaries

## Important project rule

**AI does not have authority to silently change major project decisions.**

The coding assistant may recommend alternatives, but it must ask for the owner's approval before changing any of the following:

- architecture style
- frontend or backend framework
- database technology
- queue/broker technology
- authentication strategy
- tenancy strategy
- workflow execution semantics
- database schema direction
- major dependencies
- infrastructure provider strategy
- project scope or milestone ordering

Small implementation details that do not materially change the architecture can be handled autonomously.

## How to start with Codex

1. Open this repository in VS Code.
2. Open Codex Chat.
3. Paste the contents of `CODEX_MASTER_PROMPT.md`.
4. Let Codex read `README.md` and the entire `/docs` folder.
5. Codex must first create a plan. It must **not** start coding immediately.
6. Review the plan and approve the first milestone before implementation starts.


## Local development

Prerequisites: Node.js 24, npm, Python 3.14, uv, and Docker Desktop running Linux containers.
Use `npm.cmd` in Windows PowerShell if the `npm.ps1` shim is blocked; no execution-policy change is needed.
On macOS/Linux use `npm` in the commands below.

From the repository root:

```powershell
python scripts/bootstrap_env.py
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 180
```

The environment script creates matching random credentials in ignored root/backend `.env` files
and `frontend/.env.local`. It refuses to overwrite any existing configuration. `.env.example`
files document the settings; their placeholder values are not working credentials.
Keep root credentials and backend connection URLs synchronized if editing them manually.
Changing an environment password does not rotate credentials in an already initialized database volume.

Infrastructure ports bind to `127.0.0.1`: PostgreSQL 15432, Redis 6379, RabbitMQ 5672
(management 15672), and MinIO 9000 (console 9001). Named volumes preserve local data.
PostgreSQL uses host port 15432 to avoid Windows reservations on 5432; the container still
uses 5432. To change it, update `POSTGRES_PORT` in root `.env` and the backend `DATABASE_URL` together.

MinIO's official community image endpoints were unavailable during bootstrap. Compose builds
the unmodified upstream `RELEASE.2025-10-15T17-29-55Z` from a pinned commit using
`infra/minio/Dockerfile`; base images are digest-pinned. The first build downloads Go modules
and can take several minutes. Go is only a container build tool; it is not required on the host.
The [upstream project](https://github.com/minio/minio) is source-only and no longer maintained.
This container is for local development and CI; production object storage remains an owner decision.

Start the backend in one terminal:

```powershell
cd backend
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Start the frontend in another terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. API documentation is at `http://127.0.0.1:8000/docs`.
Use `/register`, `/login`, and `/account` for registration, login, and session management. Use the same host spelling (`127.0.0.1`) for both applications. `NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000`; backend `TRUSTED_ORIGINS` defaults to `["http://127.0.0.1:3000"]`. Set both when changing origins. Verification/password-reset foundations exist; email delivery arrives in M12. See [M1 authentication](docs/13_AUTH_IMPLEMENTATION.md) for local testing links and the full contract.

Open `/organizations` after verifying your email to create/switch organizations and respond to invitations. Owners manage members and invitations at `/app/[org]/members`. Invitations appear in the recipient's account; email delivery remains M12. Use the local verification helper until delivery is implemented. See [M2 organizations](docs/14_ORGANIZATIONS_IMPLEMENTATION.md) for the lifecycle and API details.

Health endpoints are intentionally outside the `/api/v1` business prefix:

| Endpoint | Behavior |
|---|---|
| `GET /health/live` | `200 {"status":"alive"}`; no dependency checks |
| `GET /health/ready` | `200 {"status":"ready"}` after PostgreSQL `SELECT 1` and Redis `PING`; otherwise `503 {"status":"unavailable"}` |

Readiness has an overall configurable deadline, returns no connection details, and disables caching.
Redis is essential to M1 rate limiting. RabbitMQ and MinIO are checked separately by smoke tests. No migrations run on application startup.

## Checks

Backend, from `backend/`:

```powershell
uv run --locked ruff check . ../scripts
uv run --locked ruff format --check . ../scripts
uv run --locked mypy app tests scripts migrations ../scripts/bootstrap_env.py
uv run --locked pytest -m "not integration"
uv run --locked python -m scripts.smoke
$env:RUN_INTEGRATION_TESTS = "1"
uv run --locked pytest -m integration
Remove-Item Env:RUN_INTEGRATION_TESTS
uv run --locked alembic check
```

Integration tests require the running Compose stack and generated backend environment file.
They check real PostgreSQL access through both drivers, Redis authentication/PING,
RabbitMQ authentication through Celery's transport, MinIO HTTP readiness, and API readiness. Auth integration tests use disposable PostgreSQL schemas and isolated Redis namespaces, including migration round trips and concurrency checks.
MinIO bucket permissions and signed object operations belong to Milestone 13.
Unit tests run without infrastructure and exercise missing/invalid configuration, secret-safe
errors, readiness success/failure, timeouts, and dependency-independent liveness.

Frontend, from `frontend/`:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Regenerate API types after API changes: from `backend/`, run `uv run --locked python -m scripts.export_openapi`; from `frontend/`, run `npm.cmd run types:generate`.

Browser tests require the running infrastructure and backend dependencies. From `frontend/`:

```powershell
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

To use installed Microsoft Edge instead of downloading Chromium, set `$env:E2E_BROWSER_CHANNEL = "msedge"` before the test command. The browser harness creates an isolated test schema and starts its own servers on ports 3100/8100.

`typecheck` generates Next.js route types before invoking TypeScript, so it works on a fresh checkout.
To serve the production build locally, run `npm.cmd start` after `build`.
Next.js linting is a separate CI check, following its [installation guidance](https://nextjs.org/docs/app/getting-started/installation).

GitHub Actions defines these frontend/backend checks and starts isolated infrastructure with fresh
credentials for integration tests. No remote CI run is implied by passing local commands.
CI also checks migrations, generated API contracts, and browser authentication/organization flows.

Stop application terminals with Ctrl+C. From the root, `docker compose stop` stops infrastructure
while retaining containers and volumes; `docker compose down` removes containers and retains volumes.
Do not add `--volumes` unless you intend to delete local data.

## Documentation map

| File | Purpose |
|---|---|
| `docs/01_PROJECT_SCOPE.md` | Product purpose, users, features, boundaries |
| `docs/02_SYSTEM_ARCHITECTURE.md` | High-level system architecture and component responsibilities |
| `docs/03_FRONTEND.md` | Frontend technology, structure, state, routes, UI approach |
| `docs/04_BACKEND.md` | FastAPI backend architecture, layers, workers, libraries |
| `docs/05_DATABASE.md` | PostgreSQL model, tables, constraints, tenancy, indexes |
| `docs/06_WORKFLOW_ENGINE.md` | Workflow state machine, execution, retries, outbox, recovery |
| `docs/07_API_AND_REALTIME.md` | REST conventions, endpoints, errors, WebSocket events |
| `docs/08_SECURITY.md` | Authentication, RBAC, tenant isolation, API/webhook security |
| `docs/09_DEVOPS_AND_DEPLOYMENT.md` | Docker, environments, CI/CD, deployment, backups, monitoring |
| `docs/10_TESTING_AND_PERFORMANCE.md` | Unit/integration/E2E/load/reliability test strategy |
| `docs/11_IMPLEMENTATION_RULES.md` | AI governance, decision policy, engineering rules |
| `docs/12_INITIAL_ROADMAP.md` | Suggested milestone sequence from zero code to production |
| `docs/13_AUTH_IMPLEMENTATION.md` | Approved M1 session strategy, auth contract, and verification/reset testing |
| `docs/14_ORGANIZATIONS_IMPLEMENTATION.md` | M2 organization access, invitations, tenant context, API, and verification |

The PDF `FlowForge_Project_Scope.pdf` is a readable project brief for humans. The Markdown files are the implementation source of truth for the coding assistant.
