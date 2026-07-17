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
          <a href="/profile">Profile</a>
          <a href="/match">Match</a>
          <a href="/jobs">Jobs</a>
          <a href="/jobs/search">Job Search</a>
          <ApplicationNavGroup />
          <a href="/documents">Documents</a>
          <a href="/analytics">Analytics</a>
          <a href="/auth">Account</a>
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
          <a href="/profile">Profile</a>
          <a href="/match">Match</a>
          <a href="/jobs">Jobs</a>
          <a href="/jobs/search">Job Search</a>
          <ApplicationNavGroup />
          <a href="/documents">Documents</a>
          <a href="/analytics">Analytics</a>
          <a href="/auth">Login / Register</a>
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

function ApplicationNavGroup() {
  const pathname = usePathname();
  const isApplicationSection =
    pathname === "/applications" || pathname === "/materials" || pathname === "/interviews";
  const [expanded, setExpanded] = useState(pathname === "/materials" || pathname === "/interviews");

  useEffect(() => {
    const stored = window.localStorage.getItem("dalijob_applications_nav_expanded");
    if (pathname === "/materials" || pathname === "/interviews" || stored === "true") {
      setExpanded(true);
    }
  }, [pathname]);

  function toggleExpanded() {
    const next = !expanded;
    setExpanded(next);
    window.localStorage.setItem("dalijob_applications_nav_expanded", String(next));
  }

  return (
    <div className="sidebar-nav-group">
      <div className={`sidebar-nav-parent ${isApplicationSection ? "active" : ""}`}>
        <a href="/applications">Applications</a>
        <button
          type="button"
          className="sidebar-expand-button"
          aria-expanded={expanded}
          aria-controls="applications-subnavigation"
          aria-label={expanded ? "Collapse application links" : "Expand application links"}
          title={expanded ? "Collapse application links" : "Expand application links"}
          onClick={toggleExpanded}
        >
          <span className={expanded ? "expanded" : ""} aria-hidden="true">▼</span>
        </button>
      </div>
      <div
        className={`sidebar-subnav-shell ${expanded ? "expanded" : ""}`}
        id="applications-subnavigation"
        aria-hidden={!expanded}
      >
        <div className="sidebar-subnav">
          <a className={pathname === "/materials" ? "active" : ""} href="/materials" tabIndex={expanded ? undefined : -1}>Materials</a>
          <a className={pathname === "/interviews" ? "active" : ""} href="/interviews" tabIndex={expanded ? undefined : -1}>Interviews</a>
        </div>
      </div>
    </div>
  );
}
