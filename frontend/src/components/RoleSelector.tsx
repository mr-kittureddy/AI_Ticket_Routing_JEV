import clsx from "clsx";
import { UserRound } from "lucide-react";
import { useId } from "react";
import { useRole } from "@/context/RoleContext";
import type { UserRole } from "@/types/ticket";

const ROLE_BADGE: Record<UserRole, string> = {
  admin: "bg-bad/15 text-bad",
  agent: "bg-brand/15 text-brand",
  viewer: "bg-ink-subtle/20 text-ink-muted",
};

export function RoleSelector(): JSX.Element {
  const { user, users, setEmail } = useRole();
  const selectId = useId();

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={selectId} className="sr-only">
        Act as user
      </label>
      <UserRound aria-hidden="true" className="hidden h-4 w-4 text-ink-subtle sm:block" />
      <select
        id={selectId}
        value={user.email}
        onChange={(event) => setEmail(event.target.value)}
        title="Demo identity sent as the X-User-Email header. It is not verified by the backend."
        className="max-w-[13rem] rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {users.map((candidate) => (
          <option key={candidate.email} value={candidate.email}>
            {candidate.label} ({candidate.role})
          </option>
        ))}
      </select>
      <span
        className={clsx(
          "rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
          ROLE_BADGE[user.role],
        )}
      >
        {user.role}
      </span>
    </div>
  );
}
