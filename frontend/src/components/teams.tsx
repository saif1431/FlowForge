"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, ApiError } from "../lib/auth-api";
import type { components } from "../lib/api-schema";

type Team = components["schemas"]["TeamOutput"];
type TeamList = components["schemas"]["TeamList"];
type Members = components["schemas"]["MemberList"];
const empty = { items: [], next_cursor: null };

export default function Teams({ orgId, canManage, members, moreMembers, refreshAccess }: {
  orgId: string; canManage: boolean; members: Members;
  moreMembers: () => Promise<void>; refreshAccess: () => Promise<void>;
}) {
  const base = `/organizations/${orgId}/teams`;
  const [teams, setTeams] = useState<TeamList>(empty);
  const [selected, setSelected] = useState<Team | null>(null);
  const [people, setPeople] = useState<Members>(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const active = useRef(true);
  const generation = useRef(0);

  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const result = await apiRequest<TeamList>(base);
      if (active.current && current === generation.current) { setTeams(result); setError(""); }
    } catch (failure) {
      if (active.current && current === generation.current) {
        setTeams(empty); setSelected(null); setPeople(empty);
        setError(failure instanceof Error ? failure.message : "Unable to load teams.");
      }
    }
  }, [base]);

  useEffect(() => {
    active.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    return () => { active.current = false; };
  }, [load]);

  async function select(team: Team) {
    setBusy(true); setSelected(null); setPeople(empty); setError("");
    const current = ++generation.current;
    try {
      const result = await apiRequest<Members>(`${base}/${team.id}/members`);
      if (active.current && current === generation.current) { setSelected(team); setPeople(result); }
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : "Unable to load team.");
    } finally { if (active.current) setBusy(false); }
  }

  async function mutate(path: string, method: string, body?: unknown, keepSelected = true) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiRequest<Team | undefined>(path, method, body);
      if (!active.current) return;
      await load();
      if (keepSelected && selected) await select(result?.id ? result : selected);
      else { setSelected(null); setPeople(empty); }
      if (active.current) setMessage("Team changes saved.");
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) {
        setTeams(empty); setSelected(null); setPeople(empty); await refreshAccess();
      }
      if (active.current) setError(failure instanceof Error ? failure.message : "Unable to save changes.");
    } finally { if (active.current) setBusy(false); }
  }

  async function more(kind: "teams" | "people") {
    setBusy(true);
    try {
      if (kind === "teams") {
        const result = await apiRequest<TeamList>(`${base}?cursor=${teams.next_cursor}`);
        if (active.current) setTeams((previous) => ({ ...result, items: [...previous.items, ...result.items] }));
      } else if (selected) {
        const result = await apiRequest<Members>(`${base}/${selected.id}/members?cursor=${people.next_cursor}`);
        if (active.current) setPeople((previous) => ({ ...result, items: [...previous.items, ...result.items] }));
      }
    } catch (failure) {
      if (active.current) { setTeams(empty); setSelected(null); setPeople(empty); setError(failure instanceof Error ? failure.message : "Unable to load more."); }
    } finally { if (active.current) setBusy(false); }
  }

  return <section className="auth-card">
    <h2>Teams</h2><p>Group organization members into teams. Team membership does not change their permissions.</p>
    {error && <div role="alert" className="auth-error">{error} <button disabled={busy} onClick={() => void load()}>Reload teams</button></div>}
    {message && <p role="status" className="auth-success">{message}</p>}
    {canManage && <form onSubmit={(event) => { event.preventDefault(); void mutate(base, "POST", { name: new FormData(event.currentTarget).get("name") }, false); }}>
      <label>New team name<input name="name" required maxLength={120} /></label><button disabled={busy}>Create team</button>
    </form>}
    {!teams.items.length && <p>No teams to display.</p>}
    <ul className="session-list">{teams.items.map((team) => <li key={team.id}><button disabled={busy} aria-pressed={selected?.id === team.id} onClick={() => void select(team)}>{team.name}</button></li>)}</ul>
    {teams.next_cursor && <button disabled={busy} onClick={() => void more("teams")}>More teams</button>}
    {selected && <section aria-label={`Team ${selected.name}`}>
      <h3>{selected.name}</h3>
      {canManage && <><form key={selected.name} onSubmit={(event) => { event.preventDefault(); void mutate(`${base}/${selected.id}`, "PATCH", { name: new FormData(event.currentTarget).get("name") }); }}>
        <label>Team name<input name="name" required maxLength={120} defaultValue={selected.name} /></label><button disabled={busy}>Rename team</button>
      </form><button disabled={busy} onClick={() => { if (window.confirm(`Delete ${selected.name}? Organization members will remain.`)) void mutate(`${base}/${selected.id}`, "DELETE", undefined, false); }}>Delete team</button></>}
      <h4>Team members</h4>
      {!people.items.length && <p>This team has no members.</p>}
      <ul className="session-list">{people.items.map((person) => <li key={person.id}><span className="account-email">{person.email}</span>{canManage && <button disabled={busy} aria-label={`Remove ${person.email} from team`} onClick={() => void mutate(`${base}/${selected.id}/members/${person.id}`, "DELETE")}>Remove from team</button>}</li>)}</ul>
      {people.next_cursor && <button disabled={busy} onClick={() => void more("people")}>More team members</button>}
      {canManage && <form onSubmit={(event) => { event.preventDefault(); void mutate(`${base}/${selected.id}/members`, "POST", { membership_id: new FormData(event.currentTarget).get("membership_id") }); }}>
        <label htmlFor={`add-member-${selected.id}`}>Add organization member</label><select id={`add-member-${selected.id}`} name="membership_id" required defaultValue=""><option value="" disabled>Select a member</option>{members.items.filter((person) => !people.items.some((existing) => existing.id === person.id)).map((person) => <option key={person.id} value={person.id}>{person.email}</option>)}</select><button disabled={busy}>Add to team</button>
      </form>}
      {canManage && members.next_cursor && <button disabled={busy} onClick={() => void moreMembers()}>More organization members</button>}
    </section>}
  </section>;
}
