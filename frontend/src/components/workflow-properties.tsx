"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "../lib/auth-api";
import type { components } from "../lib/api-schema";
import { nodeCatalog, type WorkflowNode } from "../lib/workflow-graph";

function AssigneePicker({ orgId, kind, value, onChange }: {
  orgId: string; kind: "member" | "team"; value: string; onChange: (id: string) => void;
}) {
  const [options, setOptions] = useState<{ id: string; label: string }[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [page, setPage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const path = `/organizations/${orgId}/${kind === "member" ? "members" : "teams"}${page ? `?cursor=${page}` : ""}`;
    async function load() {
      try {
        const result = await apiRequest<components["schemas"]["MemberList"] | components["schemas"]["TeamList"]>(path, "GET", undefined, controller.signal);
        if (!active) return;
        const choices = result.items.filter((item) => !("role_code" in item) || ["owner", "admin", "approver"].includes(item.role_code)).map((item) => ({ id: item.id, label: "email" in item ? `${item.email} (${item.role_code})` : item.name }));
        setOptions((previous) => page ? [...previous, ...choices] : choices);
        setCursor(result.next_cursor ?? null); setError("");
      } catch (failure) {
        if (active) { setOptions([]); setError(failure instanceof Error ? failure.message : "Unable to load assignees."); }
      } finally { if (active) setBusy(false); }
    }
    void load();
    return () => { active = false; controller.abort(); };
  }, [orgId, kind, page, retry]);
  return <>
    <label>Approver<select value={value} disabled={busy} onChange={(event) => onChange(event.target.value)}>
      <option value="">Select {kind === "member" ? "an eligible member" : "a team"}</option>
      {value && !options.some((item) => item.id === value) && <option value={value}>Current assignment ({value})</option>}
      {options.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
    </select></label>
    {busy && <p role="status">Loading assignees…</p>}
    {error && <p role="alert">{error} <button type="button" onClick={() => { setBusy(true); setRetry(retry + 1); }}>Retry assignees</button></p>}
    {cursor && !error && <button type="button" disabled={busy} onClick={() => { setBusy(true); setPage(cursor); }}>More assignees</button>}
    <p className="builder-hint">Members must be Owners, Admins or Approvers. Teams need an eligible member. Eligibility is checked again when publishing.</p>
  </>;
}

export default function WorkflowProperties({ node, orgId, disabled, onChange, onDelete }: {
  node: WorkflowNode; orgId: string; disabled: boolean;
  onChange: (node: WorkflowNode) => void; onDelete: () => void;
}) {
  const config = node.config ?? {};
  const text = (key: string, fallback = "") => typeof config[key] === "string" ? config[key] as string : fallback;
  const number = (key: string) => typeof config[key] === "number" ? config[key] as number : "";
  const patch = (changes: NonNullable<WorkflowNode["config"]>) => onChange({ ...node, config: { ...config, ...changes } });
  const assignee = config.assignee as { kind: "member" | "team"; id: string } | null | undefined;
  const [assigneeKind, setAssigneeKind] = useState<"member" | "team">(assignee?.kind ?? "member");
  const scalarType = config.value === null || config.value === undefined ? "null" : typeof config.value;
  return <aside className="builder-properties" aria-label="Node properties">
    <h3>{nodeCatalog[node.kind].title} settings</h3>
    <fieldset disabled={disabled}>
      <label>Node label<input maxLength={120} value={node.label ?? ""} onChange={(event) => onChange({ ...node, label: event.target.value })} /></label>
      {node.kind === "approval" && <>
        <label>Assign to<select value={assigneeKind} onChange={(event) => { setAssigneeKind(event.target.value as "member" | "team"); patch({ assignee: null }); }}><option value="member">Member</option><option value="team">Team</option></select></label>
        {disabled ? <p>Assignment: {assignee ? `${assignee.kind} ${assignee.id}` : "Not configured"}</p> : <AssigneePicker key={`${orgId}:${assigneeKind}`} orgId={orgId} kind={assigneeKind} value={assignee?.id ?? ""} onChange={(id) => patch({ assignee: id ? { kind: assigneeKind, id } : null })} />}
        <label>Due after (minutes, optional)<input type="number" min={1} max={525600} step={1} value={number("due_after_minutes")} onChange={(event) => patch({ due_after_minutes: event.target.value === "" ? null : Number(event.target.value) })} /></label>
        <p className="builder-hint">One eligible approver decides. Connect both approved and rejected paths.</p>
      </>}
      {node.kind === "condition" && <>
        <label>Input field<input maxLength={200} placeholder="input.amount" value={text("field")} onChange={(event) => patch({ field: event.target.value || null })} /></label>
        <label>Comparison<select value={text("operator", "eq")} onChange={(event) => patch({ operator: event.target.value })}>
          {[['eq', 'Equals'], ['ne', 'Does not equal'], ['gt', 'Greater than'], ['gte', 'Greater than or equal'], ['lt', 'Less than'], ['lte', 'Less than or equal']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Value type<select value={scalarType} onChange={(event) => patch({ value: event.target.value === "null" ? null : event.target.value === "number" ? 0 : event.target.value === "boolean" ? true : "" })}><option value="string">Text</option><option value="number">Number</option><option value="boolean">Boolean</option><option value="null">Null</option></select></label>
        {scalarType === "boolean" ? <label>Comparison value<select value={String(config.value)} onChange={(event) => patch({ value: event.target.value === "true" })}><option value="true">True</option><option value="false">False</option></select></label> : scalarType !== "null" && <label>Comparison value<input type={scalarType === "number" ? "number" : "text"} step="any" maxLength={1000} value={String(config.value ?? "")} onChange={(event) => patch({ value: scalarType === "number" ? Number(event.target.value) : event.target.value })} /></label>}
        <p className="builder-hint">Use a field such as input.amount. Ordered comparisons need a number. Connect true and false paths.</p>
      </>}
      {node.kind === "email" && <>
        <label>Recipients (comma separated)<input value={Array.isArray(config.to) ? config.to.join(",") : ""} onChange={(event) => patch({ to: event.target.value ? event.target.value.split(",").map((item) => item.trim()) : [] })} /></label>
        <label>Email subject<input maxLength={200} value={text("subject")} onChange={(event) => patch({ subject: event.target.value })} /></label>
        <label>Email body<textarea rows={5} maxLength={4000} value={text("body")} onChange={(event) => patch({ body: event.target.value })} /></label>
        <p className="builder-hint">Up to 10 recipients. This phase saves the email definition; delivery comes later.</p>
      </>}
      {node.kind === "webhook" && <><label>Webhook URL<input type="url" maxLength={2048} placeholder="https://api.example.com/events" value={text("url")} onChange={(event) => patch({ url: event.target.value || null })} /></label><p className="builder-hint">POST to a public HTTPS URL. Credentials, query strings and fragments are not allowed. No request is sent by this editor.</p></>}
      {node.kind === "delay" && <label>Delay (seconds)<input type="number" min={1} max={2592000} step={1} value={number("seconds")} onChange={(event) => patch({ seconds: event.target.value === "" ? null : Number(event.target.value) })} /></label>}
      {node.kind === "manual_trigger" && <p className="builder-hint">The single entry point. Connect its next output to the first step.</p>}
      {node.kind === "end" && <p className="builder-hint">A terminal step. Every path must reach an End node.</p>}
      <div className="builder-coordinates">{(["x", "y"] as const).map((axis) => <label key={axis}>Position {axis.toUpperCase()}<input type="number" min={-100000} max={100000} value={node.position?.[axis] ?? 0} onChange={(event) => onChange({ ...node, position: { x: node.position?.x ?? 0, y: node.position?.y ?? 0, [axis]: Math.max(-100000, Math.min(100000, Number(event.target.value))) } })} /></label>)}</div>
      {!disabled && <button type="button" className="danger-button" onClick={onDelete}>Delete node</button>}
    </fieldset>
  </aside>;
}
