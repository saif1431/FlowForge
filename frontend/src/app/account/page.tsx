"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, authRequest, type Message, type SessionList, type User } from "../../lib/auth-api";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<SessionList["items"]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const person = await authRequest<User>("/me");
      const result = await authRequest<SessionList>("/sessions");
      setUser(person);
      setSessions(result.items);
      setError("");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        setUser(null);
        setSessions([]);
        router.replace("/login");
      } else {
        setError(failure instanceof Error ? failure.message : "Unable to load your account.");
      }
    }
  }, [router]);

  useEffect(() => {
    // Initial authenticated fetch; load updates state only after the network request settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const refresh = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, [load]);

  async function action(path: string, method = "POST", exit = false) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await authRequest<Message | undefined>(path, method);
      if (exit) {
        setUser(null);
        setSessions([]);
        router.replace("/login");
      } else {
        if (result) setMessage(result.message);
        await load();
      }
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        setUser(null);
        setSessions([]);
        router.replace("/login");
      } else setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="account-shell">
      <header className="account-header"><Link href="/" className="brand">FlowForge</Link>{user && <button disabled={busy} onClick={() => void action("/logout", "POST", true)}>Sign out</button>}</header>
      {error && <div role="alert" className="auth-error">{error} <button onClick={() => void load()}>Try again</button></div>}
      {message && <p role="status" className="auth-success">{message}</p>}
      {!user ? <p role="status">{error ? "Your account could not be loaded." : "Loading your account…"}</p> : <>
        <section className="auth-card">
          <p className="eyebrow">ACCOUNT</p>
          <h1>Your account</h1>
          <nav className="auth-links"><Link href="/organizations">Your organizations</Link></nav>
          <p className="account-email">{user.email}</p>
          <p>{user.email_verified_at ? "Email verified" : "Email not verified"}</p>
          {!user.email_verified_at && <><p>Email verification delivery is not available yet.</p><button disabled={busy} onClick={() => void action("/request-verification")}>Request verification</button></>}
        </section>
        <section className="auth-card" aria-labelledby="sessions-title">
          <h2 id="sessions-title">Active sessions</h2>
          <p>Review your sign-ins and revoke access you no longer need.</p>
          <ul className="session-list">{sessions.map((session) => <li key={session.id}>
            <div><strong>{session.current ? "This session" : "Other session"}</strong><p>Signed in {new Date(session.created_at).toLocaleString()}</p><p>Last active {new Date(session.last_seen_at).toLocaleString()}</p></div>
            <button disabled={busy} aria-label={session.current ? "Revoke this session" : `Revoke session from ${new Date(session.created_at).toLocaleString()}`} onClick={() => void action(`/sessions/${session.id}`, "DELETE", session.current)}>Revoke</button>
          </li>)}</ul>
          <button className="danger-button" disabled={busy} onClick={() => void action("/logout-all", "POST", true)}>Sign out all sessions</button>
        </section>
      </>}
    </main>
  );
}
