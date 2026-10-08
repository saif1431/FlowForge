"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, ApiError } from "../lib/auth-api";
import type { components } from "../lib/api-schema";

type Access = components["schemas"]["AccessOutput"];
type Workflow = components["schemas"]["WorkflowOutput"];
type Workflows = components["schemas"]["WorkflowList"];
type Created = components["schemas"]["WorkflowCreated"];
type Version = components["schemas"]["VersionDetail"];
type Versions = components["schemas"]["VersionList"];
type Validation = components["schemas"]["GraphValidation"];
type Graph = components["schemas"]["GraphInput"];
const empty = { items: [], next_cursor: null };

function exampleGraph(): Graph {
  const start = crypto.randomUUID(), end = crypto.randomUUID();
  return {
    nodes: [
      { id: start, kind: "manual_trigger", label: "Start", config: {}, position: { x: 0, y: 0 } },
      { id: end, kind: "end", label: "Finished", config: {}, position: { x: 300, y: 0 } },
    ],
    edges: [{ id: crypto.randomUUID(), source: start, target: end, branch: "next" }],
  };
}

export default function Workflows({ orgId, workflowId }: { orgId: string; workflowId?: string }) {
  const router = useRouter();
  const base = `/organizations/${orgId}/workflows`;
  const [access, setAccess] = useState<Access | null>(null);
  const [list, setList] = useState<Workflows>(empty);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<Versions>(empty);
  const [version, setVersion] = useState<Version | null>(null);
  const [editor, setEditor] = useState("");
  const [savedText, setSavedText] = useState("");
  const [report, setReport] = useState<Validation | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const active = useRef(true);
  const generation = useRef(0);
  const dirty = editor !== savedText;
  const can = (permission: string) => access?.permissions.includes(permission) ?? false;

  function acceptVersion(value: Version) {
    setVersion(value);
    const text = JSON.stringify(value.graph, null, 2);
    setEditor(text); setSavedText(text); setReport(null); setConflict(false);
  }

  const load = useCallback(async (preferred?: string) => {
    const current = ++generation.current;
    setLoading(true);
    try {
      const effective = await apiRequest<Access>(`/organizations/${orgId}/access`);
      if (workflowId) {
        const item = await apiRequest<Workflow>(`${base}/${workflowId}`);
        const history = await apiRequest<Versions>(`${base}/${workflowId}/versions`);
        const id = preferred ?? history.items[0]?.id;
        const selected = id ? await apiRequest<Version>(`${base}/${workflowId}/versions/${id}`) : null;
        if (!active.current || current !== generation.current) return;
        setWorkflow(item); setVersions(history); setVersion(selected);
        if (selected) acceptVersion(selected);
      } else {
        const result = await apiRequest<Workflows>(base);
        if (!active.current || current !== generation.current) return;
        setList(result);
      }
      setAccess(effective); setError("");
    } catch (failure) {
      if (!active.current || current !== generation.current) return;
      setAccess(null); setWorkflow(null); setVersion(null); setVersions(empty); setList(empty); setEditor("");
      if (failure instanceof ApiError && failure.status === 401) router.replace("/login");
      setError(failure instanceof Error ? failure.message : "Unable to load workflows.");
    } finally { if (active.current && current === generation.current) setLoading(false); }
  }, [base, orgId, workflowId, router]);

  useEffect(() => {
    active.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    return () => { active.current = false; };
  }, [load]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function failure(error: unknown) {
    if (!active.current) return;
    if (error instanceof ApiError) {
      if (error.code === "VERSION_CONFLICT" || error.code === "VERSION_IMMUTABLE") setConflict(true);
      if (Array.isArray(error.details.issues)) setReport({ valid: false, issues: error.details.issues });
      if (error.status === 401 || error.status === 404) {
        setWorkflow(null); setVersion(null); setAccess(null); setEditor(""); setList(empty);
        if (error.status === 401) router.replace("/login");
      }
      if (error.status === 403) {
        try {
          const effective = await apiRequest<Access>(`/organizations/${orgId}/access`);
          if (active.current) setAccess(effective);
        } catch { if (active.current) { setAccess(null); setWorkflow(null); setVersion(null); setEditor(""); } }
      }
    }
    if (active.current) setError(error instanceof Error ? error.message : "Unable to complete the action.");
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await apiRequest<Created>(base, "POST", { name: form.get("name"), description: form.get("description") });
      if (active.current) router.push(`/app/${orgId}/workflows/${result.workflow.id}`);
    } catch (error) { await failure(error); }
    finally { if (active.current) setBusy(false); }
  }

  async function action(kind: "save" | "validate" | "publish" | "clone") {
    if (!version || !workflowId) return;
    setBusy(true); setError(""); setMessage(""); setReport(null);
    const path = `${base}/${workflowId}/versions/${version.id}`;
    try {
      if (kind === "validate") {
        const result = await apiRequest<Validation>(`${path}/validate`, "POST", { expected_revision: version.revision });
        if (active.current) setReport(result);
      } else {
        let result: Version;
        if (kind === "save") {
          let graph: unknown;
          try { graph = JSON.parse(editor); } catch { throw new Error("The graph must contain valid JSON. Your edits have been kept."); }
          const body = { expected_revision: version.revision, graph };
          if (new TextEncoder().encode(JSON.stringify(body)).length > 16384) throw new Error("This graph exceeds the 16 KiB request limit.");
          result = await apiRequest<Version>(`${path}/graph`, "PUT", body);
        } else if (kind === "publish") {
          result = await apiRequest<Version>(`${path}/publish`, "POST", { expected_revision: version.revision });
        } else {
          result = await apiRequest<Version>(`${base}/${workflowId}/drafts`, "POST", { source_version_id: version.id });
        }
        if (!active.current) return;
        acceptVersion(result);
        setMessage(kind === "publish" ? `Version ${result.version_number} published.` : kind === "clone" ? `Draft version ${result.version_number} created.` : "Draft saved.");
        const history = await apiRequest<Versions>(`${base}/${workflowId}/versions`);
        if (active.current) setVersions(history);
      }
    } catch (error) { await failure(error); }
    finally { if (active.current) setBusy(false); }
  }

  async function more() {
    setBusy(true);
    try {
      if (workflowId) {
        const result = await apiRequest<Versions>(`${base}/${workflowId}/versions?cursor=${versions.next_cursor}`);
        if (active.current) setVersions((previous) => ({ ...result, items: [...previous.items, ...result.items] }));
      } else {
        const result = await apiRequest<Workflows>(`${base}?cursor=${list.next_cursor}`);
        if (active.current) setList((previous) => ({ ...result, items: [...previous.items, ...result.items] }));
      }
    } catch (error) { await failure(error); }
    finally { if (active.current) setBusy(false); }
  }

  function reload(id?: string) {
    if (!dirty || window.confirm("Discard your unsaved graph edits and load the saved version?")) { setMessage(""); void load(id); }
  }

  return <main className="account-shell">
    <header className="account-header"><Link className="brand" href="/organizations">FlowForge</Link><Link href="/account">Your account</Link></header>
    <nav className="auth-links" aria-label="Organization sections"><Link href={`/app/${orgId}/members`}>Members</Link><Link href={`/app/${orgId}/teams`}>Teams</Link><Link href={`/app/${orgId}/workflows`}>Workflows</Link></nav>
    {error && <div role="alert" className="auth-error">{error}{!conflict && <button disabled={busy || loading} onClick={() => reload(version?.id)}>Try again</button>}</div>}
    {message && <p role="status" className="auth-success">{message}</p>}
    {loading ? <p role="status">Loading workflows…</p> : access && <>
      {!workflowId && <section className="auth-card"><h1>Workflows</h1><p>Create and publish reusable workflow definitions. Execution becomes available in a later phase.</p>
        {can("workflow:create") && <form onSubmit={(event) => void create(event)}><label>Workflow name<input name="name" required maxLength={120} /></label><label>Description<input name="description" maxLength={1000} /></label><button disabled={busy}>Create workflow</button></form>}
        {!list.items.length && <p>No workflows yet.</p>}
        <ul className="session-list">{list.items.map((item) => <li key={item.id}><Link href={`/app/${orgId}/workflows/${item.id}`}>{item.name}</Link></li>)}</ul>
        {list.next_cursor && <button disabled={busy} onClick={() => void more()}>More workflows</button>}
      </section>}
      {workflow && <section className="auth-card"><h1>{workflow.name}</h1><p>{workflow.description}</p>
        <div className="org-actions" aria-label="Versions">{versions.items.map((item) => <button key={item.id} disabled={busy} aria-pressed={version?.id === item.id} onClick={() => reload(item.id)}>Version {item.version_number} ({item.status})</button>)}</div>
        {versions.next_cursor && <button disabled={busy} onClick={() => void more()}>Older versions</button>}
      </section>}
      {version && <section className="auth-card"><h2>Version {version.version_number}: {version.status}</h2><p>Revision {version.revision} · {version.graph.nodes?.length ?? 0} nodes · {version.graph.edges?.length ?? 0} connections</p>
        {version.status === "published" && <p>This published version is fixed. Create a new draft to make changes.</p>}
        <label htmlFor="workflow-graph">Workflow graph (JSON)</label>
        <p id="graph-help">Use node IDs to connect steps. Drafts may be incomplete; publication requires a valid graph. The visual editor arrives in M5.</p>
        <textarea id="workflow-graph" className="graph-editor" aria-describedby="graph-help" spellCheck={false} rows={18} value={editor} disabled={busy} readOnly={version.status !== "draft" || !can("workflow:edit")} onChange={(event) => { setEditor(event.target.value); setReport(null); setMessage(""); }} />
        {dirty && <p role="status">Unsaved changes. Save before validating or publishing.</p>}
        {conflict && <p role="alert">Your edits are preserved below. Copy them before reloading the saved version, then merge your changes.</p>}
        <div className="org-actions">
          {version.status === "draft" && can("workflow:edit") && <><button disabled={busy} onClick={() => { if (!dirty || window.confirm("Replace your unsaved edits with the example graph?")) { setEditor(JSON.stringify(exampleGraph(), null, 2)); setReport(null); setMessage(""); } }}>Load example graph</button><button disabled={busy || conflict} onClick={() => void action("save")}>Save draft</button></>}
          <button disabled={busy || dirty || conflict} onClick={() => void action("validate")}>Validate saved graph</button>
          {version.status === "draft" && can("workflow:publish") && <button disabled={busy || dirty || conflict} onClick={() => void action("publish")}>Publish version</button>}
          {version.status === "published" && can("workflow:edit") && !versions.items.some((item) => item.status === "draft") && <button disabled={busy} onClick={() => void action("clone")}>Create new draft</button>}
          <button disabled={busy} onClick={() => reload(version.id)}>Reload saved version</button>
        </div>
        {report && <div role={report.valid ? "status" : "alert"} className={report.valid ? "auth-success" : "auth-error"}>{report.valid ? "Graph is valid." : <><p>Resolve these issues before publishing:</p><ul>{report.issues.map((issue, index) => <li key={index}>{issue.message}{issue.node_id && <small> Node: {issue.node_id}</small>}{issue.edge_id && <small> Edge: {issue.edge_id}</small>}</li>)}</ul></>}</div>}
      </section>}
    </>}
  </main>;
}
