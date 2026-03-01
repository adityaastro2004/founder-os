import { CalendarDays } from "lucide-react";

export default function PlannerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Planner</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          AI-powered scheduling and calendar management
        </p>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 flex flex-col items-center justify-center text-center">
        <CalendarDays className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">Calendar view coming soon</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Connect your Google Calendar and let AI optimize your schedule automatically.
        </p>
      </div>
    </div>
  );
}
