import clsx from "clsx";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { getErrorMessage, getErrorRequestId, isApiError } from "@/services/api";

interface ErrorAlertProps {
  error: unknown;
  title?: string;
  /** When provided, a retry button is shown for errors where retrying can help (network, timeout, 502-504). */
  onRetry?: () => void;
  className?: string;
}

export function ErrorAlert({
  error,
  title = "Something went wrong",
  onRetry,
  className,
}: ErrorAlertProps): JSX.Element {
  const requestId = getErrorRequestId(error);
  const canRetry = onRetry !== undefined && (!isApiError(error) || error.isRetryable);

  return (
    <div
      role="alert"
      className={clsx("flex items-start gap-3 rounded-lg border border-bad/40 bg-bad/10 p-3 text-sm", className)}
    >
      <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{title}</p>
        <p className="mt-0.5 break-words text-ink-muted">{getErrorMessage(error)}</p>
        {requestId !== null && (
          <p className="mt-1 break-all font-mono text-xs text-ink-subtle">Request ID: {requestId}</p>
        )}
      </div>
      {canRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}
