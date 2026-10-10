# M4 - Workflow definitions and versioning

M4 provides workflow definitions, editable drafts, graph validation, publication,
and immutable version history. The repository already contained the feature code
when this phase was requested on 2026-10-08; this pass verifies that implementation,
adds cross-organization approval regression coverage, fixes test lint, and documents
the delivered contract. It retains the existing graph/configuration choices below.

## Where the implementation lives

| Location | Responsibility |
|---|---|
| `backend/app/modules/workflows/` | API routes, request/response schemas, tenant-scoped queries, lifecycle, graph validation |
| `backend/app/db/models.py` | Workflow, WorkflowVersion, WorkflowNode, WorkflowEdge |
| `backend/migrations/versions/0004_workflows.py` | Four tables, tenant constraints, one-draft uniqueness, immutable-version triggers, workflow permissions |
| `frontend/src/components/workflows.tsx` | Workflow creation/listing, JSON draft editing, validation, publication, version history, conflict recovery |
| `frontend/src/app/app/[org]/workflows/` | List page and `[workflowId]` detail page |
| `backend/tests/test_workflow_validation.py` | Pure graph/configuration validation tests |
| `backend/tests/test_workflows.py` | PostgreSQL API, permission, tenant, concurrency, migration and immutability tests |
| `frontend/tests/workflows.test.tsx` | Editor state, permissions, errors and conflict tests |
| `frontend/e2e/workflows.spec.ts` | Real browser create/save/publish/clone/conflict journey |
| `frontend/openapi.json`, `frontend/src/lib/api-schema.d.ts` | Generated API contract |

## Definition contract

- Creating a workflow creates empty draft version 1, revision 1.
- Each workflow has at most one draft. Saving replaces its graph atomically and
  increments its revision. Incomplete configurations may be saved; malformed
  configuration, duplicate IDs/branches and missing edge endpoints are rejected.
- Save, validate and publish require `expected_revision`. Stale requests receive
  `409 VERSION_CONFLICT`; failed operations preserve the stored graph.
- Publication validates the saved graph and current approval references, sets its
  publication timestamp and increments its revision. Invalid graphs receive
  `422 GRAPH_INVALID` with individual issues.
- Published versions cannot be edited or deleted. Both API checks and PostgreSQL
  triggers protect the version and its nodes/edges.
- A new draft copies a selected published version (or the latest when omitted).
  Version numbers increase monotonically; the published source remains unchanged.
- All operations require active verified organization membership. All six roles
  can read/validate; Owner, Admin and Designer can create/edit; only Owner and
  Admin can publish. Team membership does not grant workflow permissions.
- Tenant queries and composite foreign keys constrain resource relationships.
  Tenant and version locks serialize mutations and membership changes. Audit
  events record creation, draft creation/save and publication without graph bodies.
- Existing API CSRF, no-store responses, error redaction, 16 KiB body limit and
  shared Redis IP rate limiting apply. Workflow creation also has a per-user
  limit of 30/hour across organizations.

## Graph and node configuration

Graphs have at most 64 nodes and 128 edges, subject to the smaller effective
16 KiB request-body limit. IDs are UUIDs. Every published graph must be a DAG,
have exactly one manual trigger and at least one End, and contain only nodes
reachable from the trigger with a path to an End. Loops and parallel fork/join
are excluded. Mutually exclusive branches may converge on the same node.

| Node kind | Required outgoing branches | Configuration for publication |
|---|---|---|
| `manual_trigger` | `next` | `{}`; no incoming edges |
| `end` | None | `{}` |
| `condition` | `true`, `false` | `field` such as `input.amount`, `operator` (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`), scalar `value`; ordered comparisons require a number |
| `approval` | `approved`, `rejected` | `assignee: {kind: "member" or "team", id: UUID}`; optional `due_after_minutes` (1–525600), `decision: "any"` |
| `email` | `next` | `to` (1–10 email addresses), nonempty `subject` and `body` |
| `webhook` | `next` | Public HTTPS `url`, `method: "POST"`; credentials, query strings, fragments and private IPs rejected |
| `delay` | `next` | `seconds` (1–2592000) |

Approval member IDs are **organization membership IDs**, not user IDs. Members
must currently be Owner, Admin or Approver; teams need at least one such active
member in the same organization. Publication rechecks eligibility. Only the
`any` configuration is supported; task resolution, decision races, deadlines and
runtime reassignment belong to later execution/approval milestones.

Unknown configuration fields are rejected. No expression or node action executes
in M4. Outbound DNS/rebinding protection must be implemented with the eventual
webhook executor; URL validation here is only definition validation. Never put
credentials in labels, email content or webhook paths.

## API

At `http://127.0.0.1:8000/docs`, find the **workflows** group. All routes start
with `/api/v1/organizations/{org_id}/workflows`:

| Method | Suffix | Body/result |
|---|---|---|
| POST | (none) | `{name, description}` → workflow plus draft |
| GET | (none) | Workflow list; UUID `cursor`, `limit` (1–100) |
| GET | `/{workflow_id}` | Workflow metadata |
| GET | `/{workflow_id}/versions` | Newest-first history; version-number cursor |
| GET | `/{workflow_id}/versions/{version_id}` | Version including its graph |
| PUT | `/{workflow_id}/versions/{version_id}/graph` | `{expected_revision, graph}` |
| POST | `/{workflow_id}/versions/{version_id}/validate` | `{expected_revision}` → `{valid, issues}` |
| POST | `/{workflow_id}/versions/{version_id}/publish` | `{expected_revision}` → published version |
| POST | `/{workflow_id}/drafts` | `{source_version_id}` or `{}` → new draft |

Swagger documents the schema, but interactive writes still require the existing
session cookie, trusted Origin and `X-CSRF-Protection: 1`. For manual writes use
the UI, whose API client supplies those controls.

## Try it locally

From the repository root, with Docker Desktop running:

```powershell
docker compose up --detach --wait --wait-timeout 180
cd backend
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
```

In another terminal:

```powershell
cd frontend
npm.cmd run dev
```

1. Open `http://127.0.0.1:3000`, log in with a verified account and open
   `/organizations`. Create or open an organization, then click **Workflows**.
   The direct route is `/app/<organization-id>/workflows`.
2. Enter a name and click **Create workflow**. Publish the empty draft first:
   validation errors should appear and it should remain a draft.
3. Click **Load example graph**, **Save draft**, then **Validate saved graph**.
   Expect **Graph is valid.** Reload to confirm persistence.
4. Click **Publish version** as Owner/Admin. Version 1 becomes read-only.
5. Click **Create new draft**. Change a node label in version 2 and save it.
   Select version 1 and confirm its original graph is unchanged.
6. Open version 2 in two browser tabs. Save a change in the first, then save in
   the second. Expect a conflict, preserved local edits and a reload option.
   Copy any edits you want to retain before accepting the discard confirmation.
7. As Designer, expect authoring controls but no publish control. As Viewer,
   expect read-only graphs. API enforcement applies even if controls are bypassed.

If your account is not verified, run this from `backend/` and open the printed
local testing link (email delivery remains M12):

```powershell
uv run --locked python -m scripts.local_auth_token --email you@example.com --purpose verify_email
```

## Automated checks

From `backend/` (integration tests use disposable PostgreSQL schemas and isolated
Redis namespaces; the Compose services must be healthy):

```powershell
uv run --locked pytest tests/test_workflow_validation.py
$env:RUN_INTEGRATION_TESTS = "1"
uv run --locked pytest tests/test_workflows.py
Remove-Item Env:RUN_INTEGRATION_TESTS
uv run --locked alembic check
```

From `frontend/`:

```powershell
npm.cmd test -- tests/workflows.test.tsx
$env:E2E_BROWSER_CHANNEL = "msedge"
npm.cmd run test:e2e -- e2e/workflows.spec.ts
Remove-Item Env:E2E_BROWSER_CHANNEL
```

The browser harness builds and serves an isolated production frontend at port
3100, starts its API at port 8100 and uses disposable test data. Sequential tests
reset only their test server's Redis counters between scenarios; real limits
remain active within each scenario. Production builds avoid intermittent 404s
observed with development-server navigation during acceptance testing.
If Edge is unavailable, install Playwright Chromium as described in the
README and omit `E2E_BROWSER_CHANNEL`. Full-project check commands are in README.

M5 remains separate: React Flow canvas and property editors. Runtime execution,
approval inboxes, actual emails/webhooks and delays are also later milestones.

## Verification recorded 2026-10-08

112 backend tests passed (51 unit, 61 integration), including a new regression
rejecting foreign-organization member/team approval assignments. Ruff lint and
format, mypy, frontend lint/type checks, 18 component tests, production build,
all five Edge browser journeys and all five infrastructure smoke checks passed.
Alembic is at `0004_workflows` with no drift; API contract regeneration is stable.
Two component timeouts under concurrent load passed with `--maxWorkers=1`.
The final browser run used the isolated production build and clean scenario rate
counters; intermittent development navigation 404s are not claimed to be fixed
in Next.js itself. Remote CI was not run.
