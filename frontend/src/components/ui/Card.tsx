import clsx from "clsx";
import type { LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";

export type CardHighlight = "none" | "jev" | "gemini" | "human";

interface CardProps {
  title?: string;
  subtitle?: string;
  icon?: LucideIcon;
  /** Rendered at the right end of the header (buttons, badges). */
  action?: ReactNode;
  highlight?: CardHighlight;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

const HIGHLIGHT_CLASSES: Record<CardHighlight, string> = {
  none: "border-line",
  jev: "border-jev/40 shadow-glow-jev",
  gemini: "border-gemini/40",
  human: "border-warn/40",
};

const ICON_CLASSES: Record<CardHighlight, string> = {
  none: "text-ink-muted",
  jev: "text-jev",
  gemini: "text-gemini",
  human: "text-warn",
};

export function Card({
  title,
  subtitle,
  icon: Icon,
  action,
  highlight = "none",
  className,
  bodyClassName,
  children,
}: CardProps): JSX.Element {
  const titleId = useId();
  const hasHeader = title !== undefined || action !== undefined;

  return (
    <section
      aria-labelledby={title !== undefined ? titleId : undefined}
      className={clsx(
        "rounded-xl border bg-surface shadow-card transition-shadow duration-300",
        HIGHLIGHT_CLASSES[highlight],
        className,
      )}
    >
      {hasHeader && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex min-w-0 items-start gap-2.5">
            {Icon !== undefined && (
              <Icon aria-hidden="true" className={clsx("mt-0.5 h-4 w-4 shrink-0", ICON_CLASSES[highlight])} />
            )}
            <div className="min-w-0">
              {title !== undefined && (
                <h2 id={titleId} className="truncate text-sm font-semibold text-ink">
                  {title}
                </h2>
              )}
              {subtitle !== undefined && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
            </div>
          </div>
          {action !== undefined && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={clsx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}
