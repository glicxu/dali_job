"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { LogIn, LogOut, ShieldCheck, Trash2, UserPlus } from "lucide-react";
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
import { AlertBanner, Badge, Button, SectionHeader, ToastRegion } from "./ui";

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
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />

      {user ? (
        <div className="profile-card auth-account-card">
          <div className="profile-card-header">
            <div>
              <p className="eyebrow">Active session</p>
              <h2>{user.display_name}</h2>
              <p className="metadata">{user.email}</p>
            </div>
            <div className="button-row">
              <Badge tone={user.role === "admin" ? "warning" : "info"}>{user.role}</Badge>
              <Button type="button" variant="secondary" size="compact" icon={LogOut} onClick={signOut}>Sign Out</Button>
            </div>
          </div>
          <section className="account-security-summary">
            <ShieldCheck size={21} aria-hidden="true" />
            <div><h3>Account security</h3><p className="metadata">Authentication uses secure server-managed session cookies. Password reset links are sent to your registered email.</p></div>
          </section>
          <div className="account-danger-zone">
            <SectionHeader title="Delete account" description="This soft-deletes your account and ends all active sessions. This action is intentionally separated from normal account controls." />
            {!showDelete ? (
              <Button type="button" variant="danger" icon={Trash2} onClick={() => setShowDelete(true)}>Delete Account</Button>
            ) : (
              <div className="auth-delete-confirmation">
                <AlertBanner tone="danger">Enter your current password to confirm account deletion.</AlertBanner>
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
                  <Button type="button" variant="danger" icon={Trash2} loading={isSubmitting} disabled={!deletePassword} onClick={removeAccount}>Confirm Delete</Button>
                  <Button type="button" variant="ghost" onClick={() => setShowDelete(false)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <form className="profile-card auth-form" onSubmit={submit}>
          <SectionHeader
            title={mode === "register" ? "Create your account" : mode === "forgot" ? "Reset your password" : mode === "reset" ? "Choose a new password" : "Sign in to DaliJob"}
            description={mode === "register" ? "Register once, verify your email, and keep your career workspace private." : mode === "forgot" ? "We will send a reset link to the email registered to your account." : mode === "reset" ? "Use at least eight characters for your new password." : "Access your saved jobs, applications, documents, and AI workflows."}
          />
          {mode === "login" || mode === "register" ? (
            <div className="segmented-control" role="group" aria-label="Authentication mode">
              <button type="button" aria-pressed={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Login</button>
              <button type="button" aria-pressed={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Register</button>
            </div>
          ) : null}

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

          <Button type="submit" icon={mode === "register" ? UserPlus : LogIn} loading={isSubmitting}>
            {mode === "register" ? "Create Account" : mode === "forgot" ? "Send Reset Link" : mode === "reset" ? "Reset Password" : "Login"}
          </Button>

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
