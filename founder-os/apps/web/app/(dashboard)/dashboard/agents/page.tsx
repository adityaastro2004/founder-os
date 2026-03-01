import { Bot, Plus } from "lucide-react";

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Deploy and manage your AI agents
          </p>
        </div>
        <button className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all">
          <Plus className="w-4 h-4" />
          New Agent
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {["Research Agent", "Email Agent", "Scheduler Agent"].map((name) => (
          <div
            key={name}
            className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div>
                <p className="font-semibold text-sm">{name}</p>
                <span className="text-xs text-emerald-600 dark:text-emerald-400">
                  Running
                </span>
              </div>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Autonomous AI agent handling tasks in the background.
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
