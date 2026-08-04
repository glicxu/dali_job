"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  clearAuthToken,
  CurrentUser,
  deleteAccount,
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
  requestPasswordReset,
  resendVerification,
  resetPassword,
  verifyEmail,
} from "../lib/api";

type Mode = "login" | "register" | "forgot" | "reset";

export function AuthForm({ onAuthChange }: { onAuthChange?: (user: CurrentUser | null) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [showDelete, setShowDelete] = useState(false);
  const [actionToken, setActionToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const processedVerification = useRef("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const action = params.get("action");
    const token = params.get("token") || "";
    if (action === "reset" && token) {
      setMode("reset");
      setActionToken(token);
      return;
    }
    if (action === "verify" && token && processedVerification.current !== token) {
      processedVerification.current = token;
      setIsSubmitting(true);
      verifyEmail(token)
        .then((response) => {
          setUser(response.user);
          onAuthChange?.(response.user);
          setStatus("Email verified. You are signed in.");
          window.history.replaceState({}, "", "/auth");
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Email verification failed."))
        .finally(() => setIsSubmitting(false));
      return;
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => clearAuthToken());
  }, [onAuthChange]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsSubmitting(true);
    try {
      if (mode === "register") {
        const result = await registerUser(email, password, displayName);
        setStatus(result.message);
        setPassword("");
      } else if (mode === "forgot") {
        const result = await requestPasswordReset(email);
        setStatus(result.message);
      } else if (mode === "reset") {
        const result = await resetPassword(actionToken, password);
        setStatus(result.message);
        setPassword("");
        setMode("login");
        window.history.replaceState({}, "", "/auth");
      } else {
        const response = await loginUser(email, password);
        setUser(response.user);
        onAuthChange?.(response.user);
        setStatus("Signed in.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function signOut() {
    try {
      await logoutUser();
    } finally {
      setUser(null);
      onAuthChange?.(null);
      setStatus("Signed out.");
    }
  }

  async function removeAccount() {
    if (!window.confirm("Soft-delete your DaliJob account and sign out?")) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await deleteAccount(deletePassword);
      setUser(null);
      onAuthChange?.(null);
      setStatus("Your account has been deleted.");
      setShowDelete(false);
      setDeletePassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account deletion failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="auth-panel">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      {user ? (
        <div className="profile-card auth-account-card">
          <div>
            <h2>Signed in</h2>
            <p className="metadata">{user.email}</p>
          </div>
          <button type="button" className="secondary-button" onClick={signOut}>Sign Out</button>
          <div className="account-danger-zone">
            <h3>Delete account</h3>
            <p className="metadata">This disables your account and ends all active sessions.</p>
            {!showDelete ? (
              <button type="button" className="danger-button" onClick={() => setShowDelete(true)}>
                Delete Account
              </button>
            ) : (
              <div className="auth-delete-confirmation">
                <label>
                  Current Password
                  <input
                    autoComplete="current-password"
                    type="password"
                    value={deletePassword}
                    onChange={(event) => setDeletePassword(event.target.value)}
                  />
                </label>
                <div className="button-row">
                  <button type="button" className="danger-button" disabled={!deletePassword || isSubmitting} onClick={removeAccount}>
                    Confirm Delete
                  </button>
                  <button type="button" className="secondary-button" onClick={() => setShowDelete(false)}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <form className="profile-card auth-form" onSubmit={submit}>
          {mode !== "reset" ? (
            <div className="segmented-control" role="tablist" aria-label="Authentication mode">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Login</button>
              <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Register</button>
            </div>
          ) : <h2>Reset Password</h2>}

          {mode !== "reset" ? (
            <label>
              Email
              <input autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
          ) : null}

          {mode === "register" ? (
            <label>
              Display Name
              <input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
            </label>
          ) : null}

          {mode !== "forgot" ? (
            <label>
              {mode === "reset" ? "New Password" : "Password"}
              <input
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "login" ? 1 : 8}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
          ) : null}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Working..." : mode === "register" ? "Create Account" : mode === "forgot" ? "Send Reset Link" : mode === "reset" ? "Reset Password" : "Login"}
          </button>

          {mode === "login" ? <button type="button" className="text-button" onClick={() => setMode("forgot")}>Forgot password?</button> : null}
          {mode === "forgot" ? <button type="button" className="text-button" onClick={() => setMode("login")}>Back to login</button> : null}
          {mode === "register" && status ? (
            <button type="button" className="text-button" onClick={async () => setStatus((await resendVerification(email)).message)}>
              Resend verification email
            </button>
          ) : null}
        </form>
      )}
    </section>
  );
}
