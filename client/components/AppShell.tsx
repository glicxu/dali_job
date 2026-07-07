"use client";

import { ReactNode, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AuthForm } from "./AuthForm";
import { clearAuthToken, CurrentUser, getAuthToken, getCurrentUser } from "../lib/api";

type AuthState = "checking" | "authenticated" | "anonymous";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [user, setUser] = useState<CurrentUser | null>(null);

  function signOut() {
    clearAuthToken();
    setUser(null);
    setAuthState("anonymous");
  }

  useEffect(() => {
    if (!getAuthToken()) {
      setAuthState("anonymous");
      return;
    }
    getCurrentUser()
      .then((currentUser) => {
        setUser(currentUser);
        setAuthState("authenticated");
      })
      .catch(() => {
        clearAuthToken();
        setUser(null);
        setAuthState("anonymous");
      });
  }, []);

  if (authState === "checking") {
    return (
      <main className="content">
        <section className="panel">
          <p className="empty">Checking session.</p>
        </section>
      </main>
    );
  }

  if (authState === "anonymous") {
    if (pathname === "/auth") {
      return (
        <PublicShell>
          <section className="panel">
            <div>
              <p className="eyebrow">Account</p>
              <h1>DaliJob login</h1>
              <p className="lede">Create a DaliJob account or sign in with your existing DaliJob account.</p>
            </div>
            <AuthForm
              onAuthChange={(currentUser) => {
                setUser(currentUser);
                setAuthState(currentUser ? "authenticated" : "anonymous");
              }}
            />
          </section>
        </PublicShell>
      );
    }

    return <PublicShell>{children}</PublicShell>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">DaliJob</div>
        <nav>
          <a href="/">Home</a>
          <a href="/match">Match</a>
          <a href="/jobs">Jobs</a>
          <a href="/jobs/search">Job Search</a>
          <a href="/jobs/import">Bulk Import</a>
          <a href="/profile">Profile</a>
          <a href="/documents">Documents</a>
          <a href="/auth">Account</a>
          <a href="/health">Health</a>
          <a href="/job-url-debug">URL Debug</a>
          <button type="button" className="sidebar-link" onClick={signOut}>
            Sign Out
          </button>
        </nav>
        {user ? <p className="metadata">{user.email}</p> : null}
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell public-shell">
      <aside className="sidebar" aria-label="Public navigation">
        <div className="brand">DaliJob</div>
        <nav>
          <a href="/">Home</a>
          <a href="/match">Match</a>
          <a href="/jobs">Jobs</a>
          <a href="/jobs/search">Job Search</a>
          <a href="/jobs/import">Bulk Import</a>
          <a href="/profile">Profile</a>
          <a href="/documents">Documents</a>
          <a href="/health">Health</a>
          <a href="/job-url-debug">URL Debug</a>
          <a href="/auth">Login / Register</a>
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
