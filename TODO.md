# FlowForge - Phase-by-phase TODO

Latest completed phase: **M4 - COMPLETE** (verified 2026-10-08).
Next phase: **M5 - NOT STARTED**. Awaiting the owner's instruction to continue.

Local verification follow-up (2026-10-10): at the owner's request, the existing
backend `.env` and local bootstrap now set `REQUIRE_EMAIL_VERIFICATION=false`.
The centralized tenant authentication dependency and frontend follow the same
server policy. Existing and new accounts can use organizations/invitations/workflows
without verification; stored verification timestamps remain unchanged. Account
verification prompts are hidden. Staging/production reject the bypass. Verified
19 backend organization/configuration tests, 22 frontend tests, Ruff/mypy,
frontend lint/type checks, and all three auth browser tests against a production
build, including unverified organization creation on both local hostnames.
C: was full; test temporary files were redirected to the workspace on D:.


Authentication follow-up (2026-10-10): owner requested localhost support and explicit
duplicate-email rejection. Added local same-origin API proxying, trusted localhost
origin (including the existing local configuration), and `409 EMAIL_ALREADY_REGISTERED`.
Existing accounts/passwords are preserved; case-insensitive uniqueness and concurrent
registration are enforced by the existing database constraint. Updated API contracts
and README. Verified 19 backend auth/configuration tests, 21 frontend tests,
Ruff lint/format, mypy, frontend lint/type checking and production browser build.
All six browser scenarios passed across the main run and the focused organization
rerun after updating its response matcher for the proxy. Both hostnames cover
registration, cross-host duplicate rejection, original-password login, persisted
HttpOnly sessions and logout. Restart both local application servers to use the fix.

This checklist follows [the approved roadmap](docs/12_INITIAL_ROADMAP.md). Build one task at a time within one phase. Existing setup files are not proof that acceptance checks have passed; checked boxes require recorded verification.

## Working rules

1. Work only on the current approved phase. Explain its scope and acceptance criteria before implementation.
2. Mark a task `[x]` only after completing and verifying it. Record verification results under that phase.
3. Use statuses: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, and `COMPLETE`. Record the reason when blocked.
4. Complete a phase only when all its tasks and acceptance checks pass, relevant tests/lint/type/build checks pass, documentation is current, and no known critical regression remains.
5. Update this file and the roadmap together when phase status changes.
6. Stop at each phase boundary. Start the next phase only when the owner asks to continue.

Keep the approved order **M6 -> M9 -> M7 -> M8**. Add audit writes, authorization, tenant isolation, applicable CSRF controls, rate limits, secret redaction, and regression tests with each relevant feature; do not defer them to the later review phases.

Owner decision gates remain in place: authentication before M1, role matrix before M3, graph/approval configuration semantics before M4, and runtime retry/cancellation semantics before M6. Resolve infrastructure providers, encryption-key management, retention, recovery objectives, and optional row-level security before the work that depends on those choices. This checklist does not approve those decisions or authorize later phases.

## M0 - Verify and finish the existing project setup

Status: COMPLETE

- [x] Verify frontend/backend folders, Next.js + TypeScript, and FastAPI + uv setup.
- [x] Verify configuration, environment examples, and dependency lockfiles.
- [x] Verify Docker Compose starts PostgreSQL, Redis, RabbitMQ, and MinIO.
- [x] Verify frontend and backend start locally.
- [x] Verify health endpoints and infrastructure connectivity checks.
- [x] Verify lint, type checks, tests, frontend build, and CI configuration.
- [x] Phase complete: startup, connectivity, and baseline checks pass with evidence recorded.

Verification (2026-10-01):

- Backend Ruff lint/format and mypy passed; all 12 unit tests and 2 integration tests passed.
- Frontend lint, type checking, its 1 test, and production build passed.
- Live HTTP checks passed for the production landing page and 7 static assets, backend liveness, PostgreSQL readiness with `Cache-Control: no-store`, and API docs.
- Compose configuration validated, MinIO built successfully, and all four containers reached healthy status. All five smoke checks passed: PostgreSQL async/sync, Redis, RabbitMQ, and MinIO HTTP readiness.
- Locked backend dependency sync, frontend manifest/lockfile consistency, and installed dependency checks passed. Environment files are ignored by Git and service credentials match; no secrets were printed.
- GitHub Actions configuration was reviewed; no remote CI run is claimed. MinIO bucket permissions and signed object operations remain M13 work.
- Sandbox-only cache/temp permission errors were resolved using workspace-local paths: `UV_CACHE_DIR=D:\FastApiProjects\FlowForge\.local\uv-cache`, pytest `--basetemp ../.local/pytest-m0-unit` (or `pytest-m0-integration`) and `-o cache_dir=../.local/pytest-cache-m0`. Integration tests ran with `RUN_INTEGRATION_TESTS=1`.

No application-code changes were needed to finish M0.

## M1 - Authentication and sessions

Status: COMPLETE

- [x] Obtain the owner's authentication/session strategy decision.
- [x] Add the user model and initial Alembic migrations.
- [x] Add registration and secure password hashing.
- [x] Add login/logout and session lifecycle controls.
- [x] Add registration/login UI and a protected account page with session management.
- [x] Add email-verification and password-reset foundations; delivery completes in M12.
- [x] Persist security audit records for login/session actions.
- [x] Add authentication rate limits, redaction, and cookie/CSRF controls where applicable.
- [x] Phase complete: authentication, revocation, invalid/expired credentials, and security controls pass relevant tests.

Verification (2026-10-01): All 32 backend tests passed (17 unit and 15 integration), including real PostgreSQL migrations, concurrency, expiry/revocation, production cookies, CSRF/CORS, and Redis failure/rate limits. Ruff lint/format and mypy passed. Frontend lint, type checks, 5 component tests, 2 Playwright browser tests using installed Edge, and production build passed. Alembic `0001_auth` is applied locally; `alembic check` reported no drift. All five infrastructure smoke checks passed. Browser tests use disposable schemas and now shut down cleanly. OpenAPI and generated TypeScript types are updated; CI includes contract drift, migration, and browser checks (remote CI was not run). Chromium download timed out, so the browser tests used installed Edge successfully.

The owner-approved cookie strategy and local verification/reset testing are documented in [M1 authentication](docs/13_AUTH_IMPLEMENTATION.md). Email delivery remains M12; no email was sent.

Reverification (2026-10-02): all 32 backend tests, backend lint/format/mypy, frontend lint/type checks, 5 component tests, production build, and both browser assertions passed. Isolated browser builds from the existing development server and excluded browser artifacts from lint. Windows sandbox process cleanup required terminating only the identified test processes; final M2 verification includes a fresh browser run.

## M2 - Organizations and tenant isolation

Status: COMPLETE

- [x] Add organizations and memberships.
- [x] Add organization switching context.
- [x] Add the invitation lifecycle.
- [x] Enforce tenant-scoped repository access.
- [x] Add cross-tenant regression tests.
- [x] Phase complete: membership and invitation flows work, and users cannot access another tenant's resources.

Verification (2026-10-02):

- All 42 backend tests passed (17 unit, 25 integration), including 10 M2 tests covering tenant/resource ID substitution, verified identity, ownership checks, removal/rejoining, invitation lifecycle and concurrency, audit writes, pagination, shared limits, Redis outages, and M1-data-preserving migration.
- Ruff lint/format and mypy passed. Migration `0002_organizations` is applied locally; Alembic reports no schema drift. All five infrastructure smoke checks passed.
- Frontend lint/type checks, all 8 component tests, all 3 Edge browser tests, and production build passed. The browser journey covers two users, creation/switching, invitations, joining, foreign-tenant rejection, removal, and narrow-screen layout. Final browser execution outside the Windows sandbox cleaned up its servers successfully.
- OpenAPI/TypeScript contracts updated; regenerating OpenAPI produced no drift. CI includes both authentication and organization browser tests; remote CI was not run.
- See [M2 organizations](docs/14_ORGANIZATIONS_IMPLEMENTATION.md). Invitations use a verified-recipient inbox; email delivery remains M12. Ownership policy is deliberately limited to organization creators until the M3 role matrix is approved. No M3 work started.

## M3 - Roles, permissions, and teams

Status: COMPLETE

M2 reverification (2026-10-03): all 42 backend tests (17 unit, 25 integration), Ruff lint/format, mypy, frontend lint/type checks, 8 component tests, 3 Edge browser tests, and production build passed. All five infrastructure smoke checks passed. Local Alembic remains at `0002_organizations` with no schema drift. OpenAPI and TypeScript regeneration produced no contract changes. Browser servers shut down successfully. Docker Desktop and existing containers were started for verification; no application fixes were needed. Remote CI was not run.

The owner authorized moving to M3 after these checks. Following presentation of the [matrix and implementation plan](docs/15_M3_ROLE_MATRIX_PROPOSAL.md), the owner instructed completing M3 on 2026-10-06. Implementation uses the recommended fixed single-role matrix.

- [x] Obtain the owner's role matrix decision.
- [x] Add roles, permissions, and role-permission mappings.
- [x] Add team membership.
- [x] Add centralized backend authorization helpers.
- [x] Phase complete: allowed actions succeed and forbidden actions fail according to the approved role matrix.

Verification (2026-10-06):

- Implemented fixed Owner/Admin/Designer/Approver/Member/Viewer roles, persisted permission mappings, per-organization assignments, centralized backend permission checks, protected Owner/Admin policies, and tenant-constrained teams. Added role management and teams UI with effective-permission controls.
- All 56 backend tests passed: the full 54-test suite plus two additional targeted regressions (17 unit, 39 integration total). The 14 M3 cases cover the six-role matrix, escalation, role revocation, tenant boundaries, per-organization roles, team lifecycle/pagination, rejoining, concurrent changes/removal, database constraints, auditing, migration preservation, CSRF, rate limits, and redaction.
- Ruff lint/format and mypy passed. Migration `0003_roles_teams` is applied locally; Alembic reports no schema drift. All five infrastructure smoke checks passed.
- Frontend lint/type checks, all 12 component tests, and the final production build passed. All four Edge browser scenarios passed: the three existing scenarios in the full run and the M3 scenario in a focused rerun after correcting select labels. M3 covers Admin appointment, persisted team management, demotion rejecting an open-page write, read-only access, deletion, and a narrow screen. Both test-server ports were closed after cleanup.
- OpenAPI and TypeScript contracts regenerated without drift. CI includes the new tests; remote CI was not run. See [M3 roles and teams](docs/16_ROLES_TEAMS_IMPLEMENTATION.md) for the delivered contract.

The initial M3 source audit found M3 unimplemented; that gap was resolved. M4 completion and its retained definition semantics are recorded below.

## M4 - Workflow definitions and versioning

Status: COMPLETE

- [x] Document retained graph and approval configuration semantics from the existing implementation.
- [x] Add workflows and workflow versions.
- [x] Add nodes, edges, and graph validation.
- [x] Add draft creation and editing.
- [x] Add publication and immutable published versions.
- [x] Phase complete: valid drafts publish, invalid graphs are rejected, and published versions cannot be modified.

The owner requested M4 implementation on 2026-10-08. The initial audit found the feature code already present in the checked-in tree while the documentation still said NOT STARTED. This pass retains that implementation's DAG, explicit branch, single-draft and approval configuration choices; it does not introduce runtime execution semantics. See [M4 implementation and testing](docs/17_WORKFLOWS_IMPLEMENTATION.md).

Verification (2026-10-08):

- All 112 backend tests passed: 51 unit tests, the full 60-test integration run, and the added cross-organization approval regression (61 integration cases total). Coverage includes invalid graphs, snapshot immutability through API and direct SQL, roles, tenant/version substitution, concurrent saves/publication/cloning, audit writes, CSRF, limits, redaction and M3-preserving migrations.
- Ruff lint/format and mypy passed. Local migration is `0004_workflows`; Alembic reports no drift. All five infrastructure smoke checks passed. OpenAPI/TypeScript regeneration produced no contract changes.
- Frontend lint/type checks, all 18 component tests and production build passed. Two initial component timeouts under concurrent load passed when rerun with `--maxWorkers=1`.
- All five Edge browser scenarios passed together against the isolated production build. M4 verifies invalid publication, persisted drafts, read-only publication, cloning, unchanged history, two-tab revision conflicts and mobile width. Test servers shut down cleanly.
- Fixed cross-scenario Redis counter interference in the loopback-only browser harness; application limits remain unchanged. Browser tests now build/serve production output after intermittent development-server navigation 404s. The complete production suite passed; the development-only flake is not claimed to be fixed in Next.js.
- Added the M4 testing guide, updated README/roadmap/checklist and CI labels, and made the new guide Git-visible while keeping existing documentation ignore policy. Remote CI was not run. M5 and execution milestones remain NOT STARTED.

## M5 - Visual workflow builder

Status: NOT STARTED

- [ ] Add the React Flow canvas and custom node types.
- [ ] Add the node property editor.
- [ ] Add draft saving.
- [ ] Show validation errors and handle version conflicts.
- [ ] Phase complete: users can edit and reload a saved graph, see validation errors, and handle conflicting edits safely.

Verification: Pending.

## M6 - Execution persistence

Status: NOT STARTED

- [ ] Obtain decisions on runtime retry and cancellation semantics.
- [ ] Persist workflow executions and step executions.
- [ ] Persist attempts and execution events.
- [ ] Add transactionally safe state-machine transition utilities.
- [ ] Phase complete: execution history persists and transition tests enforce the approved states and concurrency rules.

Verification: Pending.


## M7 - Core workflow engine

Status: NOT STARTED

- [ ] Add graph traversal and the executor registry.
- [ ] Add manual trigger, condition, and end executors.
- [ ] Add context resolution.
- [ ] Add state-machine tests and asynchronous execution through the outbox.
- [ ] Phase complete: a trigger-condition-end workflow follows the correct branch and reaches a deterministic terminal state.

Verification: Pending.

## M8 - Human approvals and task inbox

Status: NOT STARTED

- [ ] Add the approval executor and durable pause/resume behavior.
- [ ] Add task inbox API and UI.
- [ ] Add authorized approve/reject actions with atomic concurrency control.
- [ ] Add task comments and pending/completed/overdue views using approved assignment and due-date policies.
- [ ] Phase complete: concurrent decisions produce one winner, unauthorized decisions fail, and approved work resumes once logically.

Verification: Pending.


## M9 - Background workers and transactional outbox

Status: NOT STARTED

- [ ] Configure RabbitMQ queues and Celery workers.
- [ ] Add thin worker tasks that use shared domain code.
- [ ] Add transactional outbox records and the publisher.
- [ ] Handle at-least-once delivery with idempotent processing.
- [ ] Phase complete: committed work survives broker outages and duplicate delivery does not duplicate business transitions.

Verification: Pending.

## M10 - Retries, scheduling, and recovery

Status: NOT STARTED

- [ ] Implement persisted retry attempts and backoff/jitter.
- [ ] Add delay nodes and scheduling without sleeping workers.
- [ ] Add leases and stale-running recovery.
- [ ] Implement the dead-letter/failure-handling strategy.
- [ ] Phase complete: retry, delay, lease expiry, and worker crash scenarios follow approved recovery semantics.

Verification: Pending.

## M11 - Realtime updates

Status: NOT STARTED

- [ ] Add authenticated and authorized WebSocket subscriptions.
- [ ] Add the Redis Pub/Sub bridge.
- [ ] Publish user, organization, and execution events.
- [ ] Add the frontend provider with reconnect and authoritative state refetch.
- [ ] Phase complete: authorized clients receive updates, unauthorized subscriptions fail, and reconnect restores current state.

Verification: Pending.

## M12 - Notifications and email

Status: NOT STARTED

- [ ] Add in-app notifications.
- [ ] Add the email delivery worker and separate delivery status from business state.
- [ ] Add the Email workflow node executor.
- [ ] Complete email-verification and password-reset delivery from M1.
- [ ] Phase complete: notifications and account emails work, expired tokens fail, and delivery failures do not corrupt business state.

Verification: Pending.

## M13 - Files and attachments

Status: NOT STARTED

- [ ] Add the object storage adapter.
- [ ] Add file metadata and attachment authorization.
- [ ] Add signed uploads and downloads.
- [ ] Phase complete: authorized file operations work, signed URLs expire, and cross-tenant file access fails.

Verification: Pending.

## M14 - Incoming and outgoing webhooks

Status: NOT STARTED

- [ ] Add API-key creation, hashed storage, scopes, expiry, revocation, and last-used metadata before key-authenticated endpoints.
- [ ] Add HMAC webhook ingress with replay and idempotency controls.
- [ ] Add the outgoing webhook executor and delivery attempts.
- [ ] Enforce SSRF controls.
- [ ] Phase complete: valid webhooks work; invalid signatures, replay, unauthorized keys, and unsafe destinations are rejected.

Verification: Pending.

## M15 - Audit history, dashboard, and analytics

Status: NOT STARTED

- [ ] Add audit browsing over records written by earlier phases.
- [ ] Add the execution dashboard.
- [ ] Add basic aggregate analytics.
- [ ] Phase complete: authorized users can inspect tenant-scoped history and dashboard figures match the test dataset.

Verification: Pending.

## M16 - Security review

Status: NOT STARTED

- [ ] Review CSRF/CORS, rate limits, and secret redaction.
- [ ] Review file protections and API-key scopes/lifecycle.
- [ ] Consolidate the security regression suite.
- [ ] Record the owner's optional row-level security decision; implement only if selected.
- [ ] Phase complete: security regressions pass and identified critical issues are resolved.

Verification: Pending.

## M17 - End-to-end validation

Status: NOT STARTED

- [ ] Test the full login, organization, workflow, publication, execution, approval, and completion journey.
- [ ] Test failure cases and tenant isolation across features.
- [ ] Test database migrations.
- [ ] Test worker crash and retry behavior.
- [ ] Phase complete: the full journey and integration, concurrency, isolation, migration, and recovery checks pass.

Verification: Pending.

## M18 - Load testing and optimization

Status: NOT STARTED

- [ ] Prepare a representative test dataset and realistic user workload.
- [ ] Run load tests at 100, 500, and 1,000 virtual users.
- [ ] Measure worker throughput and WebSocket load.
- [ ] Tune queries and indexes based on measured bottlenecks.
- [ ] Write a performance report with environment, results, and limitations.
- [ ] Phase complete: measurements and follow-up checks are recorded; performance claims reflect observed results.

Verification: Pending.

## M19 - Production deployment

Status: NOT STARTED

- [ ] Resolve remaining production provider, retention, key-management, and recovery decisions.
- [ ] Prepare staging and production CI/CD.
- [ ] Configure managed data services.
- [ ] Configure backups/point-in-time recovery and verify restoration.
- [ ] Configure monitoring and alerts.
- [ ] Document and validate deployment and rollback procedures.
- [ ] Phase complete: staging validation, recovery checks, operational monitoring, and the authorized production deployment are verified.

Verification: Pending.
