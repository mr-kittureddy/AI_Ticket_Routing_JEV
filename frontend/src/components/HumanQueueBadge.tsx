import { UserRound } from "lucide-react";

interface HumanQueueBadgeProps {
  /** The response_text of a human-assigned ticket ("Assigned to <Queue>. ..."). */
  responseText: string | null;
  /** Queue name from the trace; takes precedence over the name parsed from the response text. */
  assignedQueue: string | null;
}

const FALLBACK_QUEUE_NAME = "Human queue";

// The backend notice always starts with "Assigned to <Queue>." and queue names contain no periods.
const NOTICE_PATTERN = /^Assigned to (.+?)\.\s*([\s\S]*)$/;

export function HumanQueueBadge({ responseText, assignedQueue }: HumanQueueBadgeProps): JSX.Element {
  const match = responseText !== null ? NOTICE_PATTERN.exec(responseText.trim()) : null;
  const queueName = assignedQueue ?? match?.[1] ?? FALLBACK_QUEUE_NAME;
  const notice = match !== null ? match[2].trim() : (responseText ?? "").trim();

  return (
    <div className="space-y-3">
      <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-warn/40 bg-warn/10 px-3.5 py-1.5">
        <UserRound aria-hidden="true" className="h-4 w-4 shrink-0 text-warn" />
        <span className="min-w-0 break-words text-sm font-semibold text-ink">Assigned to {queueName}</span>
      </div>
      {notice.length > 0 && <p className="text-sm leading-relaxed text-ink-muted">{notice}</p>}
    </div>
  );
}
