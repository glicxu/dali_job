import { CheckCircle2, X } from "lucide-react";

export function ToastRegion({ message, onDismiss }: { message: string | null; onDismiss?: () => void }) {
  if (!message) return <div className="ui-toast-region" aria-live="polite" aria-atomic="true" />;
  return (
    <div className="ui-toast-region" aria-live="polite" aria-atomic="true">
      <div className="ui-toast">
        <CheckCircle2 size={18} aria-hidden="true" />
        <span>{message}</span>
        {onDismiss ? (
          <button type="button" onClick={onDismiss} aria-label="Dismiss notification" title="Dismiss notification">
            <X size={16} aria-hidden="true" />
          </button>
        ) : null}
      </div>
    </div>
  );
}
