import { MessageSquare } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Chat</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Talk to your AI agents directly
        </p>
      </div>
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 flex flex-col items-center justify-center text-center">
        <MessageSquare className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
        <h2 className="text-lg font-semibold mb-2">Start a conversation</h2>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
          Chat with your agents, ask questions, and give instructions in natural language.
        </p>
      </div>
    </div>
  );
}
