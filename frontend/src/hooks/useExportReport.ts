import { useMutation } from "@tanstack/react-query";
import { useRole } from "@/context/RoleContext";
import { downloadReport } from "@/services/api";
import type { DownloadedReport, ReportParams } from "@/types/ticket";

const REVOKE_DELAY_MS = 10_000;

/** Hands a blob to the browser as a file download using a temporary object URL. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}

export interface UseExportReportResult {
  /** True when the acting role holds reports:export; use it to disable the buttons. */
  canExport: boolean;
  exportReport: (params: ReportParams) => void;
  isExporting: boolean;
  error: Error | null;
  reset: () => void;
}

export function useExportReport(): UseExportReportResult {
  const { email, can } = useRole();
  const canExport = can("reports:export");

  const mutation = useMutation<DownloadedReport, Error, ReportParams>({
    mutationFn: async (params) => {
      const report = await downloadReport(params, { userEmail: email });
      saveBlob(report.blob, report.filename);
      return report;
    },
  });

  return {
    canExport,
    exportReport: (params) => {
      if (canExport) mutation.mutate(params);
    },
    isExporting: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
