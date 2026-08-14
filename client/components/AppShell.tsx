"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  ClipboardList,
  FileText,
  Files,
  Home,
  LogIn,
  LogOut,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Search,
  ShieldCheck,
  Target,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { AuthForm } from "./AuthForm";
import { isTutorialRouteAllowed, tutorialRouteFallback, TutorialCoachmark } from "./TutorialGuide";
import { PageHeader } from "./ui";
import { clearAuthToken, CurrentUser, getCurrentUser, logoutUser } from "../lib/api";

type AuthState = "checking" | "authenticated" | "anonymous";
type NavItem = { href: string; label: string; icon: LucideIcon; exact?: boolean };

const careerItems: NavItem[] = [
  { href: "/", label: "Home", icon: Home, exact: true },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/profile", label: "Resumes", icon: FileText },
  { href: "/jobs/search", label: "Job Search", icon: Search },
  { href: "/jobs", label: "Saved Jobs", icon: BriefcaseBusiness, exact: true },
  { href: "/match", label: "Match", icon: Target },
];

const workspaceItems: NavItem[] = [
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

function isActivePath(pathname: string, item: NavItem): boolean {
  if (item.href === "/jobs") {
    return pathname === "/jobs" || (pathname.startsWith("/jobs/") && !pathname.startsWith("/jobs/search"));
  }
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavigationLink({
  item,
  pathname,
  onNavigate,
  disabled = false,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
  disabled?: boolean;
}) {
  const Icon = item.icon;
  const active = isActivePath(pathname, item);
  if (disabled) {
    return (
      <span className="sidebar-nav-link sidebar-nav-disabled" aria-disabled="true" title="Finish Getting Started to unlock this page.">
        <Icon size={18} strokeWidth={2} aria-hidden="true" />
        <span>{item.label}</span>
      </span>
    );
  }
  return (
    <Link
      className={`sidebar-nav-link${active ? " active" : ""}`}
      href={item.href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
    >
      <Icon size={18} strokeWidth={2} aria-hidden="true" />
      <span>{item.label}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const firstRunIncomplete = authState === "authenticated" && Boolean(user && !user.tutorial_completed);
  const firstRunRouteBlocked = firstRunIncomplete && !isTutorialRouteAllowed(pathname);

  async function signOut() {
    try {
      await logoutUser();
    } finally {
      setUser(null);
      setAuthState("anonymous");
      setMobileNavOpen(false);
    }
  }

  useEffect(() => {
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

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (firstRunRouteBlocked) window.location.replace(tutorialRouteFallback());
  }, [firstRunRouteBlocked]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const sidebar = sidebarRef.current;
    const focusable = sidebar?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])');
    focusable?.[0]?.focus();
    document.body.classList.add("nav-open");

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
        menuButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("nav-open");
    };
  }, [mobileNavOpen]);

  if (authState === "checking") {
    return (
      <main className="content session-check" aria-busy="true">
        <div className="ui-session-skeleton">
          <span />
          <span />
          <span />
        </div>
        <span className="sr-only">Checking session.</span>
      </main>
    );
  }

  if (authState === "anonymous" && pathname === "/auth") {
    return (
      <PublicShell pathname={pathname} mobileNavOpen={mobileNavOpen} setMobileNavOpen={setMobileNavOpen} sidebarRef={sidebarRef} menuButtonRef={menuButtonRef}>
        <section className="panel auth-page-panel">
          <PageHeader eyebrow="Account" title="Sign in to DaliJob" description="Create an account or sign in to access your private career workspace." icon={UserRound} />
          <AuthForm
            onAuthChange={(currentUser) => {
              setUser(currentUser);
              setAuthState(currentUser ? "authenticated" : "anonymous");
              if (currentUser) {
                const destination = currentUser.tutorial_completed ? "/dashboard" : "/";
                window.setTimeout(() => window.location.replace(destination), 0);
              }
            }}
          />
        </section>
      </PublicShell>
    );
  }

  if (authState === "anonymous") {
    return (
      <PublicShell pathname={pathname} mobileNavOpen={mobileNavOpen} setMobileNavOpen={setMobileNavOpen} sidebarRef={sidebarRef} menuButtonRef={menuButtonRef}>
        {children}
      </PublicShell>
    );
  }

  if (firstRunRouteBlocked) {
    return (
      <main className="content session-check" aria-busy="true">
        <div className="ui-session-skeleton"><span /><span /><span /></div>
        <span className="sr-only">Returning to first-time setup.</span>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <MobileHeader open={mobileNavOpen} onOpen={() => setMobileNavOpen(true)} menuButtonRef={menuButtonRef} navigationLocked={firstRunIncomplete} />
      <Sidebar
        pathname={pathname}
        user={user}
        open={mobileNavOpen}
        sidebarRef={sidebarRef}
        navigationLocked={firstRunIncomplete}
        onClose={() => setMobileNavOpen(false)}
        onSignOut={() => void signOut()}
      />
      {mobileNavOpen ? <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} /> : null}
      <main className="content" id="main-content">{children}</main>
      <TutorialCoachmark />
    </div>
  );
}

function MobileHeader({
  open,
  onOpen,
  menuButtonRef,
  navigationLocked = false,
}: {
  open: boolean;
  onOpen: () => void;
  menuButtonRef: React.RefObject<HTMLButtonElement | null>;
  navigationLocked?: boolean;
}) {
  return (
    <header className="mobile-app-header">
      <Brand disabled={navigationLocked} />
      <button ref={menuButtonRef} type="button" className="mobile-menu-button" aria-label="Open navigation" aria-expanded={open} onClick={onOpen}>
        <Menu size={21} aria-hidden="true" />
      </button>
    </header>
  );
}

function Brand({ disabled = false }: { disabled?: boolean }) {
  if (disabled) {
    return (
      <span className="brand" aria-label="DaliJob">
        <span className="brand-mark" aria-hidden="true">D</span>
        <span>DaliJob</span>
      </span>
    );
  }
  return (
    <Link className="brand" href="/" aria-label="DaliJob home">
      <span className="brand-mark" aria-hidden="true">D</span>
      <span>DaliJob</span>
    </Link>
  );
}

function Sidebar({
  pathname,
  user,
  open,
  sidebarRef,
  navigationLocked,
  onClose,
  onSignOut,
}: {
  pathname: string;
  user: CurrentUser | null;
  open: boolean;
  sidebarRef: React.RefObject<HTMLElement | null>;
  navigationLocked: boolean;
  onClose: () => void;
  onSignOut: () => void;
}) {
  return (
    <aside ref={sidebarRef} className={`sidebar${open ? " mobile-open" : ""}`} aria-label="Primary navigation">
      <div className="sidebar-topline">
        <Brand disabled={navigationLocked} />
        <button type="button" className="sidebar-close" aria-label="Close navigation" onClick={onClose}>
          <X size={20} aria-hidden="true" />
        </button>
      </div>
      <nav>
        <NavSection label="Career">
          {careerItems.map((item) => <NavigationLink item={item} pathname={pathname} onNavigate={onClose} disabled={navigationLocked} key={item.href} />)}
          <ApplicationNavGroup pathname={pathname} onNavigate={onClose} disabled={navigationLocked} />
        </NavSection>
        <NavSection label="Workspace">
          {workspaceItems.map((item) => <NavigationLink item={item} pathname={pathname} onNavigate={onClose} disabled={navigationLocked} key={item.href} />)}
        </NavSection>
      </nav>
      <div className="sidebar-utility">
        {navigationLocked ? (
          <span className="sidebar-nav-link sidebar-nav-disabled" aria-disabled="true"><MessageSquareText size={18} aria-hidden="true" /><span>Ask Scout</span></span>
        ) : (
          <Link className="sidebar-scout-action" href={`/ask-scout?from=${encodeURIComponent(pathname)}`} aria-label="Open Ask Scout" onClick={onClose}>
            <MessageSquareText size={18} aria-hidden="true" />
            <span>Ask Scout</span>
          </Link>
        )}
        <NavigationLink item={{ href: "/auth", label: "Account", icon: UserRound }} pathname={pathname} onNavigate={onClose} disabled={navigationLocked} />
        {user?.role === "admin" ? <NavigationLink item={{ href: "/admin", label: "Admin", icon: ShieldCheck }} pathname={pathname} onNavigate={onClose} disabled={navigationLocked} /> : null}
        {navigationLocked ? <p className="sidebar-first-run-note">Finish Getting Started once to unlock navigation.</p> : null}
        <button type="button" className="sidebar-nav-link sidebar-sign-out" onClick={onSignOut}>
          <LogOut size={18} aria-hidden="true" />
          <span>Sign Out</span>
        </button>
        {user ? <p className="sidebar-user-email" title={user.email}>{user.email}</p> : null}
      </div>
    </aside>
  );
}

function NavSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="sidebar-section">
      <p className="sidebar-section-label">{label}</p>
      <div className="sidebar-section-links">{children}</div>
    </section>
  );
}

function PublicShell({
  children,
  pathname,
  mobileNavOpen,
  setMobileNavOpen,
  sidebarRef,
  menuButtonRef,
}: {
  children: ReactNode;
  pathname: string;
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
  sidebarRef: React.RefObject<HTMLElement | null>;
  menuButtonRef: React.RefObject<HTMLButtonElement | null>;
}) {
  return (
    <div className="app-shell public-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <MobileHeader open={mobileNavOpen} onOpen={() => setMobileNavOpen(true)} menuButtonRef={menuButtonRef} />
      <aside ref={sidebarRef} className={`sidebar${mobileNavOpen ? " mobile-open" : ""}`} aria-label="Public navigation">
        <div className="sidebar-topline">
          <Brand />
          <button type="button" className="sidebar-close" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}><X size={20} aria-hidden="true" /></button>
        </div>
        <nav>
          <NavSection label="Explore">
            {careerItems.map((item) => <NavigationLink item={item} pathname={pathname} onNavigate={() => setMobileNavOpen(false)} key={item.href} />)}
            <ApplicationNavGroup pathname={pathname} onNavigate={() => setMobileNavOpen(false)} />
            {workspaceItems.map((item) => <NavigationLink item={item} pathname={pathname} onNavigate={() => setMobileNavOpen(false)} key={item.href} />)}
          </NavSection>
        </nav>
        <div className="sidebar-utility">
          <NavigationLink item={{ href: "/auth", label: "Login / Register", icon: LogIn }} pathname={pathname} onNavigate={() => setMobileNavOpen(false)} />
        </div>
      </aside>
      {mobileNavOpen ? <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} /> : null}
      <main className="content" id="main-content">{children}</main>
    </div>
  );
}

function ApplicationNavGroup({ pathname, onNavigate, disabled = false }: { pathname: string; onNavigate?: () => void; disabled?: boolean }) {
  const isApplicationSection = pathname.startsWith("/applications") || pathname === "/materials" || pathname === "/interviews";
  const [expanded, setExpanded] = useState(pathname === "/materials" || pathname === "/interviews");

  useEffect(() => {
    const stored = window.localStorage.getItem("dalijob_applications_nav_expanded");
    if (pathname === "/materials" || pathname === "/interviews" || stored === "true") setExpanded(true);
  }, [pathname]);

  function toggleExpanded() {
    const next = !expanded;
    setExpanded(next);
    window.localStorage.setItem("dalijob_applications_nav_expanded", String(next));
  }

  if (disabled) {
    return (
      <div className="sidebar-nav-group">
        <span className="sidebar-nav-link sidebar-nav-disabled" aria-disabled="true" title="Finish Getting Started to unlock this page.">
          <ClipboardList size={18} aria-hidden="true" />
          <span>Applications</span>
        </span>
      </div>
    );
  }

  return (
    <div className="sidebar-nav-group">
      <div className={`sidebar-nav-parent${isApplicationSection ? " active" : ""}`}>
        <Link href="/applications" aria-current={pathname.startsWith("/applications") ? "page" : undefined} onClick={onNavigate}>
          <ClipboardList size={18} aria-hidden="true" />
          <span>Applications</span>
        </Link>
        <button
          type="button"
          className="sidebar-expand-button"
          aria-expanded={expanded}
          aria-controls="applications-subnavigation"
          aria-label={expanded ? "Collapse application links" : "Expand application links"}
          title={expanded ? "Collapse application links" : "Expand application links"}
          onClick={toggleExpanded}
        >
          <ChevronDown className={expanded ? "expanded" : ""} size={16} aria-hidden="true" />
        </button>
      </div>
      <div className={`sidebar-subnav-shell${expanded ? " expanded" : ""}`} id="applications-subnavigation" aria-hidden={!expanded}>
        <div className="sidebar-subnav">
          <Link className={pathname === "/materials" ? "active" : ""} href="/materials" aria-current={pathname === "/materials" ? "page" : undefined} tabIndex={expanded ? undefined : -1} onClick={onNavigate}>
            <FileText size={16} aria-hidden="true" /> Materials
          </Link>
          <Link className={pathname === "/interviews" ? "active" : ""} href="/interviews" aria-current={pathname === "/interviews" ? "page" : undefined} tabIndex={expanded ? undefined : -1} onClick={onNavigate}>
            <CalendarDays size={16} aria-hidden="true" /> Interviews
          </Link>
        </div>
      </div>
    </div>
  );
}
