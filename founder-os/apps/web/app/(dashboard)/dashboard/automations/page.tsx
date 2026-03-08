import { Zap, Plus } from "lucide-react";

export default function AutomationsPage() {
  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Automations</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Set up automated workflows powered by AI
          </p>
        </div>
        <button className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors">
          <Plus className="w-4 h-4" />
          New Automation
        </button>
      </div>
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-12 flex flex-col items-center justify-center text-center">
        <Zap className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">No automations yet</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Create workflows that trigger agents, send emails, and more — automatically.
        </p>
      </div>
    </div>
  );
}
