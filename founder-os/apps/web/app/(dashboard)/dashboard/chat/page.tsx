"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import {
  MessageSquare,
  Send,
  Bot,
  User,
  Loader2,
  Sparkles,
  Clock,
  Zap,
  GitBranch,
  AlertCircle,
  RotateCcw,
  Wrench,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface OrchestrationResponse {
  content: string;
  model: string;
  tokens_used: number;
  tool_calls_made: number;
  tool_names: string[];
  delegations_made: number;
  agents_used: string[];
  duration_seconds: number;
  stop_reason: string;
  cost_usd: number;
  llm_provider: string;
  pending_approvals: unknown[];
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  meta?: {
    model: string;
    tokens: number;
    duration: number;
    agents_used: string[];
    delegations: number;
    tool_calls: number;
    tool_names: string[];
  };
  error?: boolean;
}

/* ── Suggested Prompts ─────────────────────────────── */
const SUGGESTIONS = [
  { icon: Sparkles, text: "What can you help me with today?" },
  { icon: Zap, text: "Research the latest trends in AI agents" },
  { icon: GitBranch, text: "Draft a follow-up email to my investor meeting" },
  { icon: Clock, text: "Optimize my schedule for next week" },
];

/* ── Message Bubble ───────────────────────────────── */
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={clsx("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={clsx(
          "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
          isUser
            ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
            : "bg-gradient-to-br from-indigo-500 to-purple-600 text-white"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={clsx("max-w-[75%] space-y-2", isUser ? "items-end" : "items-start")}>
        <div
          className={clsx(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "bg-indigo-600 text-white rounded-tr-md"
              : message.error
              ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border border-red-200 dark:border-red-500/20 rounded-tl-md"
              : "bg-[var(--color-surface)] border border-[var(--color-border)] rounded-tl-md"
          )}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>

        {/* Meta info for assistant messages */}
        {message.meta && (
          <div className="flex flex-wrap gap-2 text-[10px] text-[var(--color-text-muted)]">
            {message.meta.agents_used.length > 0 && (
              <span className="flex items-center gap-1 bg-[var(--color-surface-subtle)] px-2 py-0.5 rounded-full border border-[var(--color-border)]">
                <GitBranch className="w-3 h-3" />
                {message.meta.agents_used.join(", ")}
              </span>
            )}
            {message.meta.tool_names.length > 0 && (
              <span className="flex items-center gap-1 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400">
                <Wrench className="w-3 h-3" />
                {message.meta.tool_names.join(", ")}
              </span>
            )}
            <span className="flex items-center gap-1 bg-[var(--color-surface-subtle)] px-2 py-0.5 rounded-full border border-[var(--color-border)]">
              <Clock className="w-3 h-3" />
              {message.meta.duration.toFixed(1)}s
            </span>
            <span className="flex items-center gap-1 bg-[var(--color-surface-subtle)] px-2 py-0.5 rounded-full border border-[var(--color-border)]">
              <Zap className="w-3 h-3" />
              {message.meta.tokens} tokens
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Chat Page ────────────────────────────────────── */
export default function ChatPage() {
  const api = useApi();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  const handleInputChange = (value: string) => {
    setInput(value);
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 160)}px`;
    }
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text.trim(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setLoading(true);

    try {
      const data: OrchestrationResponse = await api("/api/agents/orchestrate", {
        method: "POST",
        body: JSON.stringify({
          message: text.trim(),
          session_id: sessionId,
        }),
      });

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.content,
        timestamp: new Date(),
        meta: {
          model: data.model,
          tokens: data.tokens_used,
          duration: data.duration_seconds,
          agents_used: data.agents_used,
          delegations: data.delegations_made,
          tool_calls: data.tool_calls_made,
          tool_names: data.tool_names || [],
        },
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          err instanceof Error
            ? `Sorry, something went wrong: ${err.message}`
            : "Sorry, something went wrong. Please try again.",
        timestamp: new Date(),
        error: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold tracking-tight">Chat</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Talk to your AI agents — auto-delegates to the right specialist
        </p>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-4 space-y-4">
        {messages.length === 0 ? (
          /* Empty state with suggestions */
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8 text-white" />
            </div>
            <h2 className="text-lg font-semibold mb-2">How can I help?</h2>
            <p className="text-sm text-[var(--color-text-secondary)] max-w-sm text-center mb-6">
              Your message is routed to the best specialist agent automatically.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  onClick={() => sendMessage(s.text)}
                  className="flex items-center gap-3 p-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-indigo-300 dark:hover:border-indigo-500/30 hover:shadow-sm transition-all text-left"
                >
                  <s.icon className="w-4 h-4 text-indigo-500 shrink-0" />
                  <span className="text-sm">{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl rounded-tl-md px-4 py-3">
                  <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input bar */}
      <form
        onSubmit={handleSubmit}
        className="mt-3 flex items-end gap-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-2"
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything..."
          rows={1}
          disabled={loading}
          className="flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--color-text-muted)] disabled:opacity-50 max-h-40"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className={clsx(
            "p-2.5 rounded-xl transition-all shrink-0",
            input.trim() && !loading
              ? "bg-indigo-600 text-white hover:bg-indigo-700"
              : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
          )}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </form>
    </div>
  );
}
