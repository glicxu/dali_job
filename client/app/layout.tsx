import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "DaliJob",
  description: "AI-assisted career management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar" aria-label="Primary navigation">
            <div className="brand">DaliJob</div>
            <nav>
              <a href="/">Match</a>
              <a href="/jobs">Jobs</a>
              <a href="/profile">Profile</a>
              <a href="/documents">Documents</a>
              <a href="/job-url-debug">URL Debug</a>
              <a href="/auth">Login</a>
              <a href="/health">Health</a>
            </nav>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
