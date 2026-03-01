import { Brain } from "lucide-react";

export default function MemoryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Memory</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Your AI&apos;s long-term memory and context
        </p>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 flex flex-col items-center justify-center text-center">
        <Brain className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">Memory Graph</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Browse and manage the memories your AI agents have stored over time.
        </p>
      </div>
    </div>
  );
}
