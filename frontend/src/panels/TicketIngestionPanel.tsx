import { zodResolver } from "@hookform/resolvers/zod";
import clsx from "clsx";
import { Inbox, Loader2, RotateCcw, Send } from "lucide-react";
import { useId, useState } from "react";
import { useForm, type UseFormSetError } from "react-hook-form";
import { Card } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { DEFAULT_SUBMITTER_EMAIL, TICKET_PRESETS } from "@/lib/constants";
import { generateTicketId } from "@/lib/format";
import { RAW_TEXT_MAX_LENGTH, RAW_TEXT_MIN_LENGTH, ticketFormSchema } from "@/schemas/ticket";
import { ApiError, isApiError } from "@/services/api";
import type { TicketFormValues, TicketInput } from "@/types/ticket";

interface TicketIngestionPanelProps {
  /** True while the pipeline is processing a ticket. */
  isSubmitting: boolean;
  /** Sends the ticket; must reject on failure so the panel can show the error. */
  onSubmit: (input: TicketInput) => Promise<unknown>;
  /** Called when the form is cleared, so the page can discard the previous result. */
  onReset?: () => void;
}

const DEFAULT_VALUES: TicketFormValues = {
  raw_text: "",
  submitted_by: DEFAULT_SUBMITTER_EMAIL,
};

const FORM_FIELDS = ["raw_text", "submitted_by"] as const;

const INPUT_CLASSES =
  "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-brand";

/** Puts server-side (422) field messages onto the form; returns true when at least one field was matched. */
function applyServerFieldErrors(error: ApiError, setError: UseFormSetError<TicketFormValues>): boolean {
  const fieldErrors = error.fieldErrors();
  let mapped = false;
  for (const field of FORM_FIELDS) {
    const message = fieldErrors[field];
    if (message !== undefined) {
      setError(field, { type: "server", message });
      mapped = true;
    }
  }
  return mapped;
}

export function TicketIngestionPanel({ isSubmitting, onSubmit, onReset }: TicketIngestionPanelProps): JSX.Element {
  const presetId = useId();
  const textId = useId();
  const emailId = useId();
  const textHintId = useId();
  const [submitError, setSubmitError] = useState<unknown>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    reset,
    setFocus,
    formState: { errors, isSubmitting: formSubmitting },
  } = useForm<TicketFormValues>({
    resolver: zodResolver(ticketFormSchema),
    defaultValues: DEFAULT_VALUES,
    mode: "onTouched",
  });

  const rawText = watch("raw_text");
  const trimmedLength = rawText.trim().length;
  const overLimit = trimmedLength > RAW_TEXT_MAX_LENGTH;
  const matchingPreset = TICKET_PRESETS.find((preset) => preset.text === rawText);
  const busy = isSubmitting || formSubmitting;

  const submit = handleSubmit(async (values) => {
    setSubmitError(null);

    const send = (): Promise<unknown> =>
      onSubmit({
        ticket_id: generateTicketId(),
        raw_text: values.raw_text,
        submitted_by: values.submitted_by,
      });

    try {
      try {
        await send();
      } catch (error) {
        // A generated ID collided with an existing ticket (very unlikely); one retry with a fresh ID is safe.
        if (isApiError(error) && error.isConflict) {
          await send();
        } else {
          throw error;
        }
      }
    } catch (error) {
      if (isApiError(error) && applyServerFieldErrors(error, setError)) return;
      setSubmitError(error);
    }
  });

  const handleClear = (): void => {
    reset(DEFAULT_VALUES);
    setSubmitError(null);
    onReset?.();
  };

  const handlePresetChange = (value: string): void => {
    if (!value) {
      setValue("raw_text", "", { shouldValidate: false, shouldDirty: true });
      setTimeout(() => setFocus("raw_text"), 0);
      return;
    }
    const preset = TICKET_PRESETS.find((candidate) => candidate.id === value);
    if (preset === undefined) return;
    setValue("raw_text", preset.text, { shouldValidate: true, shouldDirty: true });
  };

  return (
    <Card
      title="Ticket Ingestion"
      subtitle="Describe an IT issue or pick a sample scenario"
      icon={Inbox}
      bodyClassName="space-y-4"
    >
      <form noValidate onSubmit={(event) => void submit(event)} className="space-y-4">
        <div>
          <label htmlFor={presetId} className="mb-1 block text-xs font-medium text-ink">
            Pre-loaded sample scenarios
          </label>
          <select
            id={presetId}
            value={matchingPreset?.id ?? ""}
            onChange={(event) => handlePresetChange(event.target.value)}
            disabled={busy}
            className={clsx(INPUT_CLASSES, "border-line disabled:opacity-60")}
          >
            <option value="">Custom ticket (type your own)</option>
            {TICKET_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={textId} className="mb-1 block text-xs font-medium text-ink">
            Ticket text
          </label>
          <textarea
            id={textId}
            rows={6}
            disabled={busy}
            placeholder="My GlobalProtect VPN keeps dropping every 10 minutes when connected to home Wi-Fi."
            aria-invalid={errors.raw_text ? true : undefined}
            aria-describedby={textHintId}
            {...register("raw_text")}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void submit();
              }
            }}
            className={clsx(
              INPUT_CLASSES,
              "resize-y disabled:opacity-60",
              errors.raw_text ? "border-bad" : "border-line",
            )}
          />
          <div id={textHintId} className="mt-1 flex items-start justify-between gap-3 text-xs">
            <span className={errors.raw_text ? "text-bad" : "text-ink-subtle"} role={errors.raw_text ? "alert" : undefined}>
              {errors.raw_text?.message ??
                `At least ${RAW_TEXT_MIN_LENGTH} characters. Press Ctrl or \u2318 + Enter to submit.`}
            </span>
            <span
              className={clsx("shrink-0 font-mono tabular-nums", overLimit ? "text-bad" : "text-ink-subtle")}
              aria-label={`${trimmedLength} of ${RAW_TEXT_MAX_LENGTH} characters`}
            >
              {trimmedLength}/{RAW_TEXT_MAX_LENGTH}
            </span>
          </div>
        </div>

        <div>
          <label htmlFor={emailId} className="mb-1 block text-xs font-medium text-ink">
            Submitted by
          </label>
          <input
            id={emailId}
            type="email"
            autoComplete="email"
            disabled={busy}
            aria-invalid={errors.submitted_by ? true : undefined}
            aria-describedby={errors.submitted_by ? `${emailId}-error` : undefined}
            {...register("submitted_by")}
            className={clsx(
              INPUT_CLASSES,
              "disabled:opacity-60",
              errors.submitted_by ? "border-bad" : "border-line",
            )}
          />
          {errors.submitted_by && (
            <p id={`${emailId}-error`} role="alert" className="mt-1 text-xs text-bad">
              {errors.submitted_by.message}
            </p>
          )}
        </div>

        {submitError !== null && (
          <ErrorAlert
            error={submitError}
            title="The ticket could not be processed"
            onRetry={() => void submit()}
          />
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-card transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            ) : (
              <Send aria-hidden="true" className="h-4 w-4" />
            )}
            {busy ? "Processing\u2026" : "Submit Ticket"}
          </button>

          <button
            type="button"
            onClick={handleClear}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RotateCcw aria-hidden="true" className="h-4 w-4" />
            Clear
          </button>
        </div>
      </form>
    </Card>
  );
}
