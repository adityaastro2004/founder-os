import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-line-subtle bg-surface px-6 py-16 text-center">
      {Icon && (
        <Icon className="mb-4 h-6 w-6 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
      )}
      <p className="font-serif text-lg font-medium text-ink">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-ink-secondary">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
