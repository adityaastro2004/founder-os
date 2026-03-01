import { BookOpen, Plus } from "lucide-react";

export default function KnowledgePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Documents and data your agents can reference
          </p>
        </div>
        <button className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all">
          <Plus className="w-4 h-4" />
          Upload
        </button>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 flex flex-col items-center justify-center text-center">
        <BookOpen className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">No documents yet</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Upload documents, notes, or links to build your knowledge base.
        </p>
      </div>
    </div>
  );
}
