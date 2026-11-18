import type { LucideIcon } from "lucide-react";
import { Zap } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { RoleSelector } from "./RoleSelector";
import { ThemeToggle } from "./ThemeToggle";

interface AppHeaderProps {
  title: string;
  subtitle?: string;
  /** Route of the link to the other page. */
  navTo: string;
  navLabel: string;
  navIcon: LucideIcon;
  /** Optional status row under the title bar (engine badges and similar). */
  children?: ReactNode;
}

export function AppHeader({
  title,
  subtitle,
  navTo,
  navLabel,
  navIcon: NavIcon,
  children,
}: AppHeaderProps): JSX.Element {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Skip to main content
      </a>

      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex w-full max-w-[1500px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span
              aria-hidden="true"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-jev/15 text-jev"
            >
              <Zap className="h-5 w-5" fill="currentColor" />
            </span>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-ink sm:text-lg">{title}</h1>
              {subtitle !== undefined && <p className="text-xs text-ink-muted">{subtitle}</p>}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              to={navTo}
              className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <NavIcon aria-hidden="true" className="h-4 w-4" />
              {navLabel}
            </Link>
            <RoleSelector />
            <ThemeToggle />
          </div>
        </div>

        {children !== undefined && (
          <div className="border-t border-line">
            <div className="mx-auto flex w-full max-w-[1500px] flex-wrap items-center gap-2 px-4 py-2 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        )}
      </header>
    </>
  );
}
