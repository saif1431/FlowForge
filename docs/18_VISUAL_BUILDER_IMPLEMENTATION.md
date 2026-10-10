# M5 - Visual workflow builder

Completed and verified on 2026-10-10 after owner authorization and M4 completion.
Frontend lint/type checks, 27 unit/component tests, production build and all 7
Edge browser journeys passed. Backend graph validation (34 tests) and workflow
integration (22 tests) passed. Desktop/mobile screenshots were inspected. See
`TODO.md` for initial failures and fixes. Remote GitHub CI was not rerun.

## Purpose

M4 supplied the workflow definition, validation and versioning APIs. M5 gives
people a visual way to author those definitions without writing graph JSON.
An organization can draw a process, configure its steps, save its draft and
publish an immutable version for the future execution engine to consume.
This phase does not start executions, send messages, call webhooks or wait for
approvals. Those operations belong to the later runtime milestones.

## Delivered interface

Open **Organizations > your organization > Workflows**, create or open a
workflow, and use its visual builder at `/app/[org]/workflows/[workflowId]`.

- A React Flow canvas with pan, zoom, fit-to-view, minimap and draggable steps.
- A palette for Manual trigger, Approval, Condition, Email, Webhook, Delay and
  End. These are the seven types supported by M4; incoming webhook triggers
  remain part of M14.
- Node settings, including labels and positions, member/team approval
  assignments, optional due times, typed condition comparisons, email fields,
  outbound webhook URLs and delay durations.
- Named output handles: `next`, `true`/`false`, `approved`/`rejected`. Drag from
  an output dot on the right to an input dot on the left. The Connections form
  provides the same operation without dragging. It also lists removable edges.
- A step list for selecting nodes without using the canvas. Numeric position
  inputs provide an alternative to dragging. The layout stacks on small screens.
- Draft saving, saved-graph validation, publication, history and cloning from
  M4. Saved node positions and configuration reload from PostgreSQL.
- Node-specific validation highlighting and the authoritative issue list.
  Duplicate output connections, self-loops, cycles and edges into the trigger
  are rejected in the editor. Backend validation remains authoritative.
- Unsaved-change warnings for reload, version changes, page unload and the
  editor's navigation links. Browser back navigation can still leave the route;
  use Save draft before navigating away.
- Conflict recovery keeps local edits, blocks saving and offers an explicit
  reload/discard choice. Copy local graph JSON first if those changes matter.
- Advanced JSON editing remains available for diagnostics and recovery. Invalid
  JSON or graph shapes pause the canvas rather than discarding local input.

Owner/Admin can edit and publish. Designer can edit but cannot publish. Other
roles can inspect the graph and its properties. Published versions are always
read-only. Existing backend session, tenant, permission, CSRF, revision, audit
and rate-limit controls apply to every API request. No new API or migration was
needed. Graph limits remain 64 nodes, 128 edges and a 16 KiB request body.
Approval member choices are filtered to Owner/Admin/Approver; teams are checked
by the backend for eligible members. Choices are paginated. Missing or revoked
assignments remain visible and must be resolved before publication.

## Implementation locations

| File | Responsibility |
| --- | --- |
| `frontend/src/components/workflows.tsx` | Version lifecycle, API operations, errors, permissions and lazy loading |
| `frontend/src/components/workflow-builder.tsx` | Canvas, custom node renderer, palette, selection and connections |
| `frontend/src/components/workflow-properties.tsx` | Node settings and organization-scoped approval choices |
| `frontend/src/lib/workflow-graph.ts` | Graph types, safe canvas parsing, connection rules and deletion |
| `frontend/src/lib/workflow-draft.ts` | Per-editor Zustand draft store shared by visual and JSON views |
| `frontend/src/app/globals.css` | Responsive builder styles |
| `frontend/tests/workflow-*.test.*` | Graph and settings regressions |
| `frontend/e2e/workflow-builder.spec.ts` | Real-browser acceptance against the API |

Draft stores are scoped to the mounted workflow and never persisted in browser
storage. The JSON text is the lossless shared graph representation; canvas nodes
and edges are derived from it. Server versions, effective permissions and API
responses stay with the existing M4 lifecycle component. No broad state or
API-client migration is included.

## Manual acceptance test

Start the infrastructure and API using README commands. After pulling these
changes, run `npm.cmd ci` in `frontend` and restart `npm.cmd run dev`.

1. Sign in at `http://127.0.0.1:3000` or `http://localhost:3000`, open an
   organization, then Workflows. Create **Expense routing**.
2. Add Manual trigger, Condition and End. Select Condition and set its label
   to **Amount check**, input field to `input.amount`, comparison to Greater
   than, value type to Number and comparison value to `5000`.
3. Connect Manual trigger's `next` output to Amount check. Connect Amount
   check's `true` output to End. Use handles or open Connections and use the
   From step / Output branch / To step controls.
4. Save draft, then Validate saved graph. Expect an issue on Amount check
   because its `false` branch is missing. Connect that branch to End too.
5. Drag a node to another position, change a label, save, and refresh. Check
   that the connections, typed comparison and positions remain. Validate again;
   expect **Graph is valid.**
6. Open the draft in two tabs. Change and save a label in the first. Change and
   save in the second. Expect a conflict; the second tab's edits remain visible
   and Save is disabled. Open Advanced graph JSON to copy those edits, then
   Reload saved version. Cancel preserves edits; accepting loads the winner.
7. Publish as Owner/Admin. Confirm the palette and edit controls disappear and
   settings are disabled. Create new draft to edit the next version. The old
   published version must keep its original graph.
8. Try Designer and Viewer memberships. Designer has draft editing but no
   publishing; Viewer sees read-only graphs. An API write after role revocation
   must be rejected even if the editor was already open.
9. Optionally add each other type and inspect its settings. Delete a node and
   confirm its connections disappear. Try a narrow browser window and the
   Connections form. None of these actions executes the workflow.

## Automated checks

From `frontend`:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --maxWorkers=1
npm.cmd run build
$env:E2E_BROWSER_CHANNEL = "msedge"
npm.cmd run test:e2e
Remove-Item Env:E2E_BROWSER_CHANNEL
```

The browser harness builds isolated production output and starts its own API
and frontend on 8100/3100. It uses disposable PostgreSQL schemas and test-only
rate-limit namespaces. Infrastructure must be running. Alternatively install
Playwright Chromium using the README and omit the Edge environment variable.

Backend regressions, from `backend`:

```powershell
uv run --locked pytest tests/test_workflow_validation.py
$env:RUN_INTEGRATION_TESTS = "1"
uv run --locked pytest tests/test_workflows.py
Remove-Item Env:RUN_INTEGRATION_TESTS
```

M6 remains separate and requires the owner's runtime retry/cancellation
decisions before implementation.
