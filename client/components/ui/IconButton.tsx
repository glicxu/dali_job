import { ButtonHTMLAttributes } from "react";
import { LucideIcon } from "lucide-react";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: LucideIcon;
  label: string;
  variant?: "secondary" | "ghost" | "danger";
};

export function IconButton({ icon: Icon, label, variant = "ghost", className = "", ...props }: IconButtonProps) {
  return (
    <button
      className={`ui-icon-button ui-button-${variant} ${className}`.trim()}
      aria-label={label}
      title={label}
      {...props}
    >
      <Icon size={18} aria-hidden="true" />
    </button>
  );
}
