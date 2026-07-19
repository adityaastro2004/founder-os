export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center gap-0.5 rounded border border-line bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-ink-secondary">
      {children}
    </kbd>
  );
}
