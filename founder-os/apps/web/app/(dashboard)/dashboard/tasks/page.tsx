import { ListTodo, Plus } from "lucide-react";

export default function TasksPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Tasks</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Track and manage your task queue
          </p>
        </div>
        <button className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all">
          <Plus className="w-4 h-4" />
          New Task
        </button>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 flex flex-col items-center justify-center text-center">
        <ListTodo className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">No tasks yet</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Create your first task or let an agent generate tasks for you.
        </p>
      </div>
    </div>
  );
}
