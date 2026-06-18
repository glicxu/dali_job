"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  clearAuthToken,
  CurrentUser,
  getAuthToken,
  getCurrentUser,
  loginUser,
  registerUser,
} from "../lib/api";

type Mode = "login" | "register";

export function AuthForm() {
  const [mode, setMode] = useState<Mode>("login");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!getAuthToken()) return;
    getCurrentUser()
      .then(setUser)
      .catch(() => {
        clearAuthToken();
      });
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsSubmitting(true);
    try {
      const response =
        mode === "register"
          ? await registerUser(email, password, displayName)
          : await loginUser(email, password);
      setUser(response.user);
      setStatus(mode === "register" ? "Account created." : "Signed in.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function signOut() {
    clearAuthToken();
    setUser(null);
    setStatus("Signed out.");
  }

  return (
    <section className="auth-panel">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      {user ? (
        <div className="profile-card">
          <div>
            <h2>Signed in</h2>
            <p className="metadata">{user.email}</p>
          </div>
          <button type="button" className="secondary-button" onClick={signOut}>
            Sign Out
          </button>
        </div>
      ) : (
        <form className="profile-card auth-form" onSubmit={submit}>
          <div className="segmented-control" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              Register
            </button>
          </div>

          <label>
            Email
            <input
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          {mode === "register" ? (
            <label>
              Display Name
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
              />
            </label>
          ) : null}

          <label>
            Password
            <input
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              minLength={mode === "register" ? 8 : 1}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Working..." : mode === "register" ? "Create Account" : "Login"}
          </button>
        </form>
      )}
    </section>
  );
}
