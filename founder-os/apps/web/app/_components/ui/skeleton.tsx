import { clsx } from "clsx";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx("animate-pulse rounded-control bg-surface-muted", className)}
      aria-hidden="true"
    />
  );
}
