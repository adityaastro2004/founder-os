"use client";

import { useEffect, useRef } from "react";
import { clsx } from "clsx";
import { X } from "lucide-react";

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  className,
  side = "center",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  /** "center" is the default modal; "right" is a full-height slide-over used
   *  for detail panels where the list behind should stay visible. */
  side?: "center" | "right";
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const isSheet = side === "right";

  return (
    <div
      className={clsx(
        "fixed inset-0 z-50 flex",
        isSheet ? "justify-end" : "items-center justify-center p-4",
      )}
    >
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 cursor-default bg-ink/20"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={clsx(
          "relative flex flex-col border-line bg-surface shadow-xl focus:outline-none",
          isSheet
            ? "h-full w-full max-w-md animate-slide-in-right border-l"
            : "w-full max-w-md rounded-card border",
          className,
        )}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-line-subtle px-5 py-4">
          <h2 className="font-serif text-base font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-m-2 rounded-control p-2 text-ink-muted transition-colors duration-150 hover:bg-surface-muted hover:text-ink"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className={clsx("px-5 py-4", isSheet && "flex-1 overflow-y-auto")}>
          {children}
        </div>
        {footer && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-line-subtle px-5 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
