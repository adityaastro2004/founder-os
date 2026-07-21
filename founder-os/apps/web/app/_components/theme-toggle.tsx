"use client";

import { Moon, Sun } from "lucide-react";
import clsx from "clsx";
import { useTheme } from "./theme";

export function ThemeToggle({
  variant = "icon",
  className,
}: {
  /** "icon" = compact square button; "row" = full-width sidebar-nav style */
  variant?: "icon" | "row";
  className?: string;
}) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";
  const Icon = isDark ? Sun : Moon;

  if (variant === "row") {
    return (
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={label}
        className={clsx(
          "flex w-full items-center gap-2.5 rounded-control px-2.5 py-2 text-sm text-ink-secondary transition-colors hover:bg-surface-muted hover:text-ink",
          className
        )}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        {isDark ? "Light mode" : "Dark mode"}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      className={clsx(
        "flex h-10 w-10 items-center justify-center rounded-control text-ink-secondary transition-colors hover:bg-surface-muted hover:text-ink",
        className
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}
