"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiRequest, type User } from "../lib/auth-api";
import type { components } from "../lib/api-schema";
import Teams from "./teams";

type Org = components["schemas"]["OrganizationOutput"];
type OrgList = components["schemas"]["OrganizationList"];
type Members = components["schemas"]["MemberList"];
type Invitations = components["schemas"]["InvitationList"];
type Access = components["schemas"]["AccessOutput"];
type Roles = components["schemas"]["RoleList"];
const empty = { items: [], next_cursor: null };

export default function Organizations({ orgId, view = "members" }: { orgId?: string; view?: "members" | "teams" }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<OrgList>(empty);
  const [org, setOrg] = useState<Org | null>(null);
  const [members, setMembers] = useState<Members>(empty);
  const [invites, setInvites] = useState<Invitations>(empty);
  const [access, setAccess] = useState<Access | null>(null);
  const [roles, setRoles] = useState<Roles>({ items: [] });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const active = useRef(true);
  const can = (permission: string) => access?.permissions.includes(permission) ?? false;
  const base = orgId ? `/organizations/${orgId}` : "/organizations";

  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const person = await apiRequest<User>("/auth/me");
      if (!active.current || current !== generation.current) return;
      setUser(person);
      if (!person.email_verified_at) { setLoading(false); return; }
      const organizations = await apiRequest<OrgList>("/organizations");
      const selected = orgId ? await apiRequest<Org>(`/organizations/${orgId}`) : null;
      const effective = orgId ? await apiRequest<Access>(`/organizations/${orgId}/access`) : null;
      const catalog = orgId ? await apiRequest<Roles>(`/organizations/${orgId}/roles`) : { items: [] };
      const people = orgId ? await apiRequest<Members>(`/organizations/${orgId}/members`) : empty;
      const invitations = !orgId || effective?.permissions.includes("invitation:manage")
        ? await apiRequest<Invitations>(orgId ? `/organizations/${orgId}/invitations` : "/invitations") : empty;
      if (!active.current || current !== generation.current) return;
      setOrgs(organizations); setOrg(selected); setMembers(people); setInvites(invitations); setError("");
      setAccess(effective); setRoles(catalog);
    } catch (failure) {
      if (!active.current || current !== generation.current) return;
      setOrg(null); setMembers(empty); setInvites(empty); setOrgs(empty);
      setAccess(null); setRoles({ items: [] });
      if (failure instanceof ApiError && failure.status === 401) { setUser(null); router.replace("/login"); }
      else setError(failure instanceof Error ? failure.message : "Unable to load organizations.");
    } finally {
      if (active.current && current === generation.current) setLoading(false);
    }
  }, [orgId, router]);

  useEffect(() => {
    active.current = true;
    // Network completion updates state; generation checks discard superseded requests.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const refresh = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", refresh);
    return () => { active.current = false; document.removeEventListener("visibilitychange", refresh); };
  }, [load]);

  async function action(path: string, method: string, body?: unknown, navigate = false) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiRequest<Org | undefined>(path, method, body);
      if (!active.current) return;
      if (navigate && result) router.push(`/app/${result.id}/members`);
      else { setMessage("Changes saved."); await load(); }
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof ApiError && failure.status === 401) {
        setUser(null); setOrg(null); setMembers(empty); setInvites(empty); router.replace("/login");
      } else {
        if (failure instanceof ApiError && failure.status === 403) await load();
        if (failure instanceof ApiError && failure.status === 404) { setOrg(null); setMembers(empty); setInvites(empty); }
        setError(failure instanceof Error ? failure.message : "Please try again.");
      }
    } finally { if (active.current) setBusy(false); }
  }

  async function more(kind: "organizations" | "members" | "invitations") {
    setBusy(true);
    try {
      if (kind === "organizations") {
        const next = await apiRequest<OrgList>(`/organizations?cursor=${orgs.next_cursor}`);
        if (active.current) setOrgs((previous) => ({ ...next, items: [...previous.items, ...next.items] }));
      } else if (kind === "members") {
        const next = await apiRequest<Members>(`${base}/members?cursor=${members.next_cursor}`);
        if (active.current) setMembers((previous) => ({ ...next, items: [...previous.items, ...next.items] }));
      } else {
        const next = await apiRequest<Invitations>(`${orgId ? base : ""}/invitations?cursor=${invites.next_cursor}`);
        if (active.current) setInvites((previous) => ({ ...next, items: [...previous.items, ...next.items] }));
      }
    } catch (failure) {
      if (active.current) {
        setOrg(null); setMembers(empty); setInvites(empty); setOrgs(empty);
        setError(failure instanceof Error ? failure.message : "Unable to load more.");
      }
    } finally { if (active.current) setBusy(false); }
  }

  return <main className="account-shell">
    <header className="account-header"><Link className="brand" href="/organizations">FlowForge</Link><Link href="/account">Your account</Link></header>
    {error && <div className="auth-error" role="alert">{error} <button onClick={() => void load()}>Try again</button></div>}
    {message && <p className="auth-success" role="status">{message}</p>}
    {loading ? <p role="status">Loading organizations…</p> : user && !user.email_verified_at ?
      <section className="auth-card"><h1>Verify your email</h1><p>Verify your email before creating an organization or responding to invitations.</p><Link href="/account">Go to your account</Link></section> : user && <>
      <section className="auth-card">
        <h1>{org ? org.name : "Your organizations"}</h1>
        <nav className="auth-links" aria-label="Organizations">{orgs.items.map((item) => <Link aria-current={item.id === orgId ? "page" : undefined} key={item.id} href={`/app/${item.id}/members`}>{item.name}</Link>)}<Link href="/organizations">Create or join an organization</Link></nav>
        {orgs.next_cursor && <button disabled={busy} onClick={() => void more("organizations")}>More organizations</button>}
        {!orgId && <form onSubmit={(event) => { event.preventDefault(); void action("/organizations", "POST", { name: new FormData(event.currentTarget).get("name") }, true); }}>
          <label>Organization name<input name="name" required maxLength={120} /></label><button disabled={busy}>Create organization</button>
        </form>}
        {org && <nav className="auth-links" aria-label="Organization sections"><Link href={`/app/${org.id}/members`}>Members</Link><Link href={`/app/${org.id}/teams`}>Teams</Link><Link href={`/app/${org.id}/workflows`}>Workflows</Link></nav>}
        {org && can("organization:update") && <form key={org.name} onSubmit={(event) => { event.preventDefault(); void action(base, "PATCH", { name: new FormData(event.currentTarget).get("name") }); }}>
          <label>Organization name<input name="name" required maxLength={120} defaultValue={org.name} /></label><button disabled={busy}>Save name</button>
        </form>}
      </section>
      {org && view === "teams" && <Teams key={`${org.id}:${access?.role_code}`} orgId={org.id} canManage={can("team:manage")} members={members} moreMembers={() => more("members")} refreshAccess={load} />}
      {org && view === "members" && <section className="auth-card"><h2>Members</h2><ul className="session-list">{members.items.map((member) => <li key={member.id}>
        <div><span className="account-email">{member.email}</span><p>{roles.items.find((role) => role.code === member.role_code)?.name ?? member.role_code}</p></div>
        {member.user_id !== org.owner_user_id && member.user_id !== user.id && can("role:assign") && (member.role_code !== "admin" || can("role:assign_admin")) && <form key={`${member.id}:${member.role_code}`} onSubmit={(event) => { event.preventDefault(); void action(`${base}/members/${member.id}/role`, "PATCH", { role_code: new FormData(event.currentTarget).get("role_code") }); }}>
          <label htmlFor={`role-${member.id}`}>Role for {member.email}</label><select id={`role-${member.id}`} name="role_code" defaultValue={member.role_code} disabled={busy}>{roles.items.filter((role) => role.code !== "owner" && (role.code !== "admin" || can("role:assign_admin"))).map((role) => <option key={role.code} value={role.code}>{role.name}</option>)}</select>
          <button disabled={busy}>Save role</button>
        </form>}
        {member.user_id !== org.owner_user_id && (member.user_id === user.id ? can("membership:leave") : can("member:remove") && (member.role_code !== "admin" || can("role:assign_admin"))) && <button disabled={busy} onClick={() => {
          if (window.confirm(member.user_id === user.id ? "Leave this organization?" : `Remove ${member.email} from this organization?`)) void action(`${base}/members/${member.id}`, "DELETE");
        }}>{member.user_id === user.id ? "Leave organization" : "Remove member"}</button>}
      </li>)}</ul>{members.next_cursor && <button disabled={busy} onClick={() => void more("members")}>More members</button>}</section>}
      {(!orgId || (org && view === "members" && can("invitation:manage"))) && <section className="auth-card"><h2>{orgId ? "Invitations" : "Your invitations"}</h2>
        {orgId && <><form onSubmit={(event) => { event.preventDefault(); void action(`${base}/invitations`, "POST", { email: new FormData(event.currentTarget).get("email") }); }}>
          <label>Invite email address<input name="email" type="email" required maxLength={320} /></label><button disabled={busy}>Invite member</button>
        </form><p>Invitations appear in the recipient’s account. Email delivery is not available yet.</p></>}
        {!invites.items.length && <p>No invitations yet.</p>}
        <ul className="session-list">{invites.items.map((invite) => <li key={invite.id}>
          <div><strong className="account-email">{orgId ? invite.email : invite.organization_name}</strong><p>{invite.status} · Expires {new Date(invite.expires_at).toLocaleDateString()}</p></div>
          {invite.status === "pending" && <div className="org-actions">{orgId ? <>
            <button disabled={busy} onClick={() => void action(`${base}/invitations/${invite.id}/renew`, "POST")}>Extend invitation</button>
            <button disabled={busy} onClick={() => void action(`${base}/invitations/${invite.id}`, "DELETE")}>Revoke invitation</button>
          </> : <>
            <button disabled={busy} onClick={() => void action(`/invitations/${invite.id}/accept`, "POST")}>Accept invitation</button>
            <button disabled={busy} onClick={() => void action(`/invitations/${invite.id}/decline`, "POST")}>Decline invitation</button>
          </>}</div>}
        </li>)}</ul>{invites.next_cursor && <button disabled={busy} onClick={() => void more("invitations")}>More invitations</button>}
      </section>}
    </>}
  </main>;
}
