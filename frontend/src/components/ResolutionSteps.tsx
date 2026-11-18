import { Check, ClipboardCopy, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { parseResolutionSteps } from "@/lib/format";

interface ResolutionStepsProps {
  /** Gemini's response text ("1. ...\n2. ..."). */
  text: string;
}

type CopyState = "idle" | "copied" | "failed";

const COPY_FEEDBACK_MS = 2000;

export function ResolutionSteps({ text }: ResolutionStepsProps): JSX.Element {
  const steps = useMemo(() => parseResolutionSteps(text), [text]);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const resetTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    },
    [],
  );

  const handleCopy = async (): Promise<void> => {
    let next: CopyState = "copied";
    try {
      // navigator.clipboard is undefined outside secure contexts; the resulting TypeError is handled here.
      await navigator.clipboard.writeText(text);
    } catch {
      next = "failed";
    }
    setCopyState(next);
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopyState("idle"), COPY_FEEDBACK_MS);
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium text-ink">
          Resolution steps <span className="font-normal text-ink-subtle">({steps.length})</span>
        </h3>
        <button
          type="button"
          onClick={() => void handleCopy()}
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-xs font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {copyState === "copied" ? (
            <Check aria-hidden="true" className="h-3.5 w-3.5 text-ok" />
          ) : copyState === "failed" ? (
            <TriangleAlert aria-hidden="true" className="h-3.5 w-3.5 text-bad" />
          ) : (
            <ClipboardCopy aria-hidden="true" className="h-3.5 w-3.5" />
          )}
          {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
        </button>
      </div>
      <span role="status" className="sr-only">
        {copyState === "copied" ? "Resolution steps copied to the clipboard" : ""}
        {copyState === "failed" ? "Could not copy the resolution steps" : ""}
      </span>

      {steps.length === 0 ? (
        <p className="text-sm text-ink-muted">The resolution did not contain any steps.</p>
      ) : (
        <ol className="space-y-2.5">
          {steps.map((step, index) => (
            <li key={`${index}-${step}`} className="flex gap-3">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gemini/15 text-xs font-semibold text-gemini"
              >
                {index + 1}
              </span>
              <p className="min-w-0 break-words text-sm leading-relaxed text-ink">{step}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
