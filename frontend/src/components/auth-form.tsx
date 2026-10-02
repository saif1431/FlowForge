"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authRequest, type Message } from "../lib/auth-api";

type Mode = "login" | "register" | "forgot-password" | "reset-password" | "verify-email";
const titles: Record<Mode, string> = {
  login: "Welcome back",
  register: "Create your account",
  "forgot-password": "Reset your password",
  "reset-password": "Choose a new password",
  "verify-email": "Verify your email",
};

export default function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [token, setToken] = useState("");
  const initialToken = useRef<string | null>(null);
  const needsToken = mode === "reset-password" || mode === "verify-email";
  const needsEmail = mode === "login" || mode === "register" || mode === "forgot-password";
  const needsPassword = mode === "login" || mode === "register" || mode === "reset-password";

  useEffect(() => {
    if (needsToken) {
      if (initialToken.current === null) {
        initialToken.current = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
      }
      const value = initialToken.current;
      // The fragment is browser-only: read after hydration, preserving it across Strict Mode replay.
      setToken(value);
      // Remove the secret from browser history immediately. Never persist it in browser storage.
      if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
      if (!value) setError("This link is missing its token. Please request a new link.");
    }
  }, [needsToken]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const result = await authRequest<Message>(`/${mode}`, "POST", {
        ...(needsEmail ? { email: data.get("email") } : {}),
        ...(needsPassword ? { password: data.get("password") } : {}),
        ...(needsToken ? { token } : {}),
      });
      form.reset();
      if (mode === "login") {
        router.replace("/account");
      } else {
        setMessage(result.message);
        if (needsToken) setToken("");
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <Link href="/" className="brand">FlowForge</Link>
      <section className="auth-card" aria-labelledby="auth-title">
        <p className="eyebrow">YOUR WORK, CONNECTED</p>
        <h1 id="auth-title">{titles[mode]}</h1>
        {mode === "register" && <p>Start with your personal account. Use a password of 15–128 characters.</p>}
        {mode === "forgot-password" && <p>Email delivery is not available yet. Password recovery will be available when email delivery is enabled.</p>}
        {error && <p role="alert" className="auth-error">{error}</p>}
        {message && <p role="status" className="auth-success">{message}</p>}
        {!message && (
          <form onSubmit={submit} aria-busy={busy}>
            {needsEmail && <label>Email address<input name="email" type="email" autoComplete="email" maxLength={320} required /></label>}
            {needsPassword && <label>Password<input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? 1 : 15} maxLength={128} required /></label>}
            <button className="primary-button" disabled={busy || (needsToken && !token)} type="submit">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : mode === "register" ? "Create account" : mode === "verify-email" ? "Verify email" : mode === "reset-password" ? "Update password" : "Request reset"}
            </button>
          </form>
        )}
        <nav className="auth-links" aria-label="Account links">
          {mode !== "login" && <Link href="/login">Sign in</Link>}
          {mode === "login" && <><Link href="/register">Create an account</Link><Link href="/forgot-password">Forgot password?</Link></>}
          {mode === "verify-email" && <Link href="/account">Return to account</Link>}
        </nav>
      </section>
    </main>
  );
}
