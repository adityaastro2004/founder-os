"use client";

import { clsx } from "clsx";

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={clsx(
        "inline-flex items-center gap-1 rounded-control border border-line bg-surface p-1",
        className,
      )}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            "rounded-[6px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-150",
            active === tab.id
              ? "bg-surface-muted text-ink"
              : "text-ink-secondary hover:text-ink",
          )}
        >
          {tab.label}
          {typeof tab.count === "number" && (
            <span className="ml-1.5 text-xs text-ink-muted">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
