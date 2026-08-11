import { ReactNode } from "react";

export function Toolbar({ children, label, className = "" }: { children: ReactNode; label: string; className?: string }) {
  return <div className={`ui-toolbar ${className}`.trim()} role="toolbar" aria-label={label}>{children}</div>;
}
