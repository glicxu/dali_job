import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
import "./styles/tokens.css";
import "./styles.css";
import "./styles/overhaul.css";

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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
