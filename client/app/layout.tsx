import type { Metadata } from "next";
import { AppShell } from "../components/AppShell";
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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
