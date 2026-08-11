import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { ReactNode } from "react";

type AlertTone = "info" | "success" | "warning" | "danger";

const icons = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  danger: AlertCircle,
};

export function AlertBanner({ children, tone = "info" }: { children: ReactNode; tone?: AlertTone }) {
  const Icon = icons[tone];
  return (
    <div className={`ui-alert ui-alert-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={19} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}
