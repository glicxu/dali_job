import { ReactNode } from "react";

export function WorkspaceSplitPane({ list, detail, className = "" }: { list: ReactNode; detail: ReactNode; className?: string }) {
  return (
    <div className={`ui-workspace-split ${className}`.trim()}>
      <div className="ui-workspace-list">{list}</div>
      <aside className="ui-workspace-detail">{detail}</aside>
    </div>
  );
}
