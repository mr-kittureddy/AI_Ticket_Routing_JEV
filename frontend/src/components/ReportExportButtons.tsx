import clsx from "clsx";
import { FileSpreadsheet, FileText, Loader2, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useExportReport } from "@/hooks/useExportReport";
import type { ReportFormat } from "@/types/ticket";
import { ErrorAlert } from "./ui/ErrorAlert";

interface ReportExportButtonsProps {
  /** The analytics window the page is showing, so the report covers the same period; undefined means all time. */
  windowDays?: number;
  className?: string;
}

const FORMATS: readonly { format: ReportFormat; label: string; icon: LucideIcon }[] = [
  { format: "csv", label: "Export CSV", icon: FileSpreadsheet },
  { format: "pdf", label: "Export PDF", icon: FileText },
];

export function ReportExportButtons({ windowDays, className }: ReportExportButtonsProps): JSX.Element {
  const { canExport, exportReport, isExporting, error, reset } = useExportReport();
  const [activeFormat, setActiveFormat] = useState<ReportFormat | null>(null);

  const handleExport = (format: ReportFormat): void => {
    setActiveFormat(format);
    exportReport({ format, windowDays });
  };

  return (
    <div className={clsx("space-y-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {FORMATS.map(({ format, label, icon: Icon }) => {
          const busy = isExporting && activeFormat === format;
          return (
            <button
              key={format}
              type="button"
              onClick={() => handleExport(format)}
              disabled={!canExport || isExporting}
              title={canExport ? undefined : "Your role cannot export reports. Switch to Agent or Admin."}
              className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? (
                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />
              ) : (
                <Icon aria-hidden="true" className="h-4 w-4" />
              )}
              {busy ? "Preparing\u2026" : label}
            </button>
          );
        })}
      </div>

      {!canExport && (
        <p className="text-xs text-ink-muted">
          Exporting reports needs the Agent or Admin role. Use the role selector in the header to switch.
        </p>
      )}

      <span role="status" className="sr-only">
        {isExporting ? "Preparing the report" : ""}
      </span>

      {error !== null && (
        <ErrorAlert
          error={error}
          title="Could not export the report"
          onRetry={
            activeFormat !== null
              ? () => {
                  reset();
                  handleExport(activeFormat);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}
