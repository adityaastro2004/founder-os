"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@clerk/nextjs";
import { DIRECT_API_URL } from "@/lib/api";
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

/** Intermediate streaming event from the SSE endpoint */
interface StreamingEvent {
  type: string;
  tool_name?: string;
  agent?: string;
  is_error?: boolean;
  duration_ms?: number;
  timestamp?: number;
  // done-event fields
  content?: string;
  model?: string;
  tokens_used?: number;
  tool_calls_made?: number;
  tool_names?: string[];
  delegations_made?: number;
  agents_used?: string[];
  duration_seconds?: number;
  stop_reason?: string;
  cost_usd?: number;
  llm_provider?: string;
  pending_approvals?: unknown[];
  error?: string;
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
          "w-8 h-8 rounded-md flex items-center justify-center shrink-0",
          isUser
            ? "bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]"
            : "bg-[var(--color-accent)] text-[var(--color-accent-foreground)]"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={clsx("max-w-[85%] sm:max-w-[75%] space-y-2", isUser ? "items-end" : "items-start")}>
        <div
          className={clsx(
            "rounded-lg px-4 py-3 text-sm leading-relaxed",
            isUser
              ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] rounded-tr-sm"
              : message.error
              ? "bg-[var(--color-danger)]/5 text-[var(--color-danger)] border border-[var(--color-danger)]/20 rounded-tl-sm"
              : "bg-[var(--color-surface)] border border-[var(--color-border)] rounded-tl-sm"
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
              <span className="flex items-center gap-1 bg-[var(--color-surface-subtle)] px-2 py-0.5 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)]">
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
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingEvents, setStreamingEvents] = useState<StreamingEvent[]>([]);
  const [sessionId] = useState(() => {
    if (typeof window === "undefined") return crypto.randomUUID();
    const key = "orchestrator-chat-session-id";
    const stored = localStorage.getItem(key);
    if (stored) return stored;
    const id = crypto.randomUUID();
    localStorage.setItem(key, id);
    return id;
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load persisted chat messages on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(
          `${DIRECT_API_URL}/api/history/chat/${encodeURIComponent(sessionId)}`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          }
        );
        if (!res.ok) return;
        const data = await res.json();
        // API returns a plain array of ChatMessageOut, not {messages: [...]}
        const msgs = Array.isArray(data) ? data : data.messages;
        if (cancelled || !Array.isArray(msgs) || msgs.length === 0) return;
        const restored: ChatMessage[] = msgs.map((m: Record<string, unknown>) => ({
          id: (m.id as string) || crypto.randomUUID(),
          role: m.role as "user" | "assistant",
          content: m.content as string,
          timestamp: new Date(m.created_at as string),
          ...(m.role === "assistant" && m.tokens_used
            ? {
                meta: {
                  model: (m.model as string) || "",
                  tokens: (m.tokens_used as number) || 0,
                  duration: (m.duration_seconds as number) || 0,
                  agents_used: (m.agents_used as string[]) || [],
                  delegations: (m.delegations_made as number) || 0,
                  tool_calls: 0,
                  tool_names: (m.tool_names as string[]) || [],
                },
              }
            : {}),
        }));
        setMessages(restored);
      } catch {
        // Silently ignore — first load or API unavailable
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, getToken]);

  // Abort any in-flight request on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Auto-scroll on new messages or streaming events
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingEvents]);

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
    setStreamingEvents([]);

    // Cancel any previous request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = await getToken();

      // Try SSE streaming endpoint first
      const res = await fetch(`${DIRECT_API_URL}/api/agents/orchestrate/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: text.trim(),
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        // Fallback to non-streaming endpoint
        const data: OrchestrationResponse = await api("/api/agents/orchestrate", {
          method: "POST",
          body: JSON.stringify({
            message: text.trim(),
            session_id: sessionId,
          }),
        });
        addAssistantMessage(data);
        return;
      }

      // Parse SSE stream
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event: StreamingEvent = JSON.parse(line.slice(6));

            if (event.type === "done") {
              // Final response — create the assistant message
              addAssistantMessage({
                content: event.content || "",
                model: event.model || "",
                tokens_used: event.tokens_used || 0,
                tool_calls_made: event.tool_calls_made || 0,
                tool_names: event.tool_names || [],
                delegations_made: event.delegations_made || 0,
                agents_used: event.agents_used || [],
                duration_seconds: event.duration_seconds || 0,
                stop_reason: event.stop_reason || "",
                cost_usd: event.cost_usd || 0,
                llm_provider: event.llm_provider || "",
                pending_approvals: event.pending_approvals || [],
              });
              setStreamingEvents([]);
            } else if (event.type === "error") {
              throw new Error(event.error || "Agent error");
            } else if (event.type !== "thinking") {
              // Show intermediate events (tool_call, tool_result, agent_started, etc.)
              setStreamingEvents((prev) => [...prev, event]);
            }
          } catch (parseErr) {
            // Ignore non-JSON SSE lines
            if (parseErr instanceof SyntaxError) continue;
            throw parseErr;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
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
      setStreamingEvents([]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const addAssistantMessage = (data: OrchestrationResponse) => {
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
    <div className="flex flex-col h-[calc(100dvh-8rem)]">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold tracking-tight">Chat</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Talk to your AI agents — auto-delegates to the right specialist
        </p>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-subtle)] p-4 space-y-4">
        {messages.length === 0 ? (
          /* Empty state with suggestions */
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-14 h-14 rounded-lg bg-[var(--color-accent)] flex items-center justify-center mb-4">
              <MessageSquare className="w-7 h-7 text-[var(--color-accent-foreground)]" />
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
                  className="flex items-center gap-3 p-3 rounded-lg border border-[var(--color-border-subtle)] bg-white hover:bg-[var(--color-surface-muted)] transition-colors text-left"
                >
                  <s.icon className="w-4 h-4 text-[var(--color-text-secondary)] shrink-0" />
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
                <div className="w-8 h-8 rounded-md bg-[var(--color-accent)] flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-[var(--color-accent-foreground)]" />
                </div>
                <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg rounded-tl-sm px-4 py-3 space-y-2 max-w-[85%] sm:max-w-[75%]">
                  {streamingEvents.length === 0 ? (
                    <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Thinking...</span>
                    </div>
                  ) : (
                    <>
                      {streamingEvents.map((evt, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          {evt.type === "tool_call" && (
                            <>
                              <Wrench className="w-3.5 h-3.5 text-[var(--color-warning)] animate-pulse" />
                              <span className="text-[var(--color-text-secondary)]">
                                Calling <span className="font-mono font-medium">{evt.tool_name}</span>
                                {evt.agent && <span className="text-[var(--color-text-muted)]"> via {evt.agent}</span>}
                              </span>
                            </>
                          )}
                          {evt.type === "tool_result" && (
                            <>
                              {evt.is_error ? (
                                <AlertCircle className="w-3.5 h-3.5 text-[var(--color-danger)]" />
                              ) : (
                                <Zap className="w-3.5 h-3.5 text-[var(--color-success)]" />
                              )}
                              <span className={evt.is_error ? "text-[var(--color-danger)]" : "text-[var(--color-success)]"}>
                                {evt.tool_name} {evt.is_error ? "failed" : "done"}
                                {evt.duration_ms ? ` (${evt.duration_ms}ms)` : ""}
                              </span>
                            </>
                          )}
                          {evt.type === "agent_started" && (
                            <>
                              <GitBranch className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
                              <span className="text-[var(--color-text-secondary)]">
                                Delegating to <span className="font-medium">{evt.agent}</span>
                              </span>
                            </>
                          )}
                          {evt.type === "agent_completed" && (
                            <>
                              <GitBranch className="w-3.5 h-3.5 text-[var(--color-success)]" />
                              <span className="text-[var(--color-success)]">
                                <span className="font-medium">{evt.agent}</span> finished
                              </span>
                            </>
                          )}
                          {evt.type === "started" && (
                            <>
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-text-muted)]" />
                              <span className="text-[var(--color-text-secondary)]">Agent started...</span>
                            </>
                          )}
                        </div>
                      ))}
                      <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Processing...</span>
                      </div>
                    </>
                  )}
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
        className="mt-3 flex items-end gap-2 bg-white border border-[var(--color-border-subtle)] rounded-lg p-2"
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
            "p-2.5 rounded-md transition-all shrink-0",
            input.trim() && !loading
              ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent-hover)]"
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
