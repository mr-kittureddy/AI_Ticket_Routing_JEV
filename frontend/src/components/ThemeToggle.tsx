import clsx from "clsx";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useTheme, type ThemePreference } from "@/context/ThemeContext";

const OPTIONS: readonly { value: ThemePreference; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light theme", icon: Sun },
  { value: "dark", label: "Dark theme", icon: Moon },
  { value: "system", label: "Match system theme", icon: Monitor },
];

export function ThemeToggle(): JSX.Element {
  const { preference, setPreference } = useTheme();

  return (
    <div role="group" aria-label="Color theme" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={label}
            title={label}
            onClick={() => setPreference(value)}
            className={clsx(
              "rounded-md p-1.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              active ? "bg-raised text-ink" : "text-ink-subtle hover:text-ink",
            )}
          >
            <Icon aria-hidden="true" className="h-4 w-4" />
          </button>
        );
      })}
    </div>
  );
}
