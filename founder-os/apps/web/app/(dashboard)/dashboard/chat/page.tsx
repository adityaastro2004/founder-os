"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import {
  useChatStore,
  EMPTY_SESSION,
  type ChatMessage,
} from "@/lib/chat-store";
import {
  Send,
  Loader2,
  Sparkles,
  Clock,
  Zap,
  GitBranch,
  AlertCircle,
  Wrench,
} from "lucide-react";
import { clsx } from "clsx";

// Chat state and the in-flight run live in ChatProvider (dashboard layout),
// so navigating to another tab never interrupts a running agent.

/* ── Suggested prompts ─────────────────────────────── */
const SUGGESTIONS = [
  { icon: Sparkles, text: "What can you help me with today?" },
  { icon: Zap, text: "Research the latest trends in AI agents" },
  { icon: GitBranch, text: "Draft a follow-up email to my investor meeting" },
  { icon: Clock, text: "Optimize my schedule for next week" },
];

/* ── Meta chip ────────────────────────────────────── */
function MetaChip({
  icon: Icon,
  children,
}: {
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <span className="flex items-center gap-1 rounded-full border border-line bg-surface px-2 py-0.5 text-ink-secondary">
      <Icon className="h-3 w-3" aria-hidden="true" />
      {children}
    </span>
  );
}

/* ── Message ──────────────────────────────────────── */
function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-muted px-4 py-2.5 text-sm leading-relaxed text-ink sm:max-w-[75%]">
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        className={clsx(
          "text-sm leading-relaxed",
          message.error
            ? "rounded-card border border-danger/20 bg-danger-soft px-4 py-3 text-danger"
            : "text-ink"
        )}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>

      {/* Meta info for assistant messages */}
      {message.meta && (
        <div className="flex flex-wrap gap-2 text-[10px]">
          {message.meta.agents_used.length > 0 && (
            <MetaChip icon={GitBranch}>
              {message.meta.agents_used.join(", ")}
            </MetaChip>
          )}
          {message.meta.tool_names.length > 0 && (
            <MetaChip icon={Wrench}>{message.meta.tool_names.join(", ")}</MetaChip>
          )}
          <MetaChip icon={Clock}>{message.meta.duration.toFixed(1)}s</MetaChip>
          <MetaChip icon={Zap}>{message.meta.tokens} tokens</MetaChip>
        </div>
      )}
    </div>
  );
}

/* ── Chat page ────────────────────────────────────── */
export default function ChatPage() {
  const { sessions, ensureHistory, sendOrchestrator } = useChatStore();
  const [input, setInput] = useState("");
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

  const session = sessions[sessionId] ?? EMPTY_SESSION;
  const { messages, pending: loading, streamingEvents } = session;

  // Load persisted chat messages (once per session, provider-cached)
  useEffect(() => {
    ensureHistory(sessionId, "orchestrator");
  }, [sessionId, ensureHistory]);

  // Prefill from an "Add automation" hand-off (Automations tab → Chat).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const pending = sessionStorage.getItem("fos-pending-chat-prompt");
    if (pending) {
      sessionStorage.removeItem("fos-pending-chat-prompt");
      setInput(pending);
      inputRef.current?.focus();
    }
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

  const sendMessage = (text: string) => {
    if (!text.trim() || loading) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    void sendOrchestrator(sessionId, text).finally(() => {
      inputRef.current?.focus();
    });
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
    <div className="mx-auto flex h-[calc(100dvh-8rem)] max-w-3xl flex-col">
      {/* Messages area */}
      <div className="flex-1 space-y-6 overflow-y-auto py-4">
        {messages.length === 0 ? (
          /* Empty state with suggestions */
          <div className="flex h-full flex-col items-center justify-center px-4">
            <h1 className="mb-2 font-serif text-3xl font-semibold tracking-tight text-ink">
              How can I help?
            </h1>
            <p className="mb-8 max-w-sm text-center text-sm text-ink-secondary">
              Your message is routed to the best specialist agent automatically.
            </p>
            <div className="grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  type="button"
                  onClick={() => sendMessage(s.text)}
                  className="flex items-center gap-3 rounded-card border border-line bg-surface p-3 text-left transition-colors duration-150 hover:bg-surface-muted/50"
                >
                  <s.icon
                    className="h-4 w-4 shrink-0 text-ink-secondary"
                    aria-hidden="true"
                  />
                  <span className="text-sm text-ink">{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <Message key={msg.id} message={msg} />
            ))}
            {loading && (
              <div className="space-y-2 text-xs">
                {streamingEvents.length === 0 ? (
                  <div className="flex items-center gap-2 text-sm text-ink-secondary">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    <span>Thinking</span>
                  </div>
                ) : (
                  <>
                    {streamingEvents.map((evt, i) => (
                      <div key={i} className="flex items-center gap-2">
                        {evt.type === "tool_call" && (
                          <>
                            <Wrench
                              className="h-3.5 w-3.5 animate-pulse text-warning"
                              aria-hidden="true"
                            />
                            <span className="text-ink-secondary">
                              Calling{" "}
                              <span className="font-mono font-medium">
                                {evt.tool_name}
                              </span>
                              {evt.agent && (
                                <span className="text-ink-secondary"> via {evt.agent}</span>
                              )}
                            </span>
                          </>
                        )}
                        {evt.type === "tool_result" && (
                          <>
                            {evt.is_error ? (
                              <AlertCircle
                                className="h-3.5 w-3.5 text-danger"
                                aria-hidden="true"
                              />
                            ) : (
                              <Zap
                                className="h-3.5 w-3.5 text-success"
                                aria-hidden="true"
                              />
                            )}
                            <span className={evt.is_error ? "text-danger" : "text-success"}>
                              {evt.tool_name} {evt.is_error ? "failed" : "done"}
                              {evt.duration_ms ? ` (${evt.duration_ms}ms)` : ""}
                            </span>
                          </>
                        )}
                        {evt.type === "agent_started" && (
                          <>
                            <GitBranch
                              className="h-3.5 w-3.5 text-ink-secondary"
                              aria-hidden="true"
                            />
                            <span className="text-ink-secondary">
                              Delegating to <span className="font-medium">{evt.agent}</span>
                            </span>
                          </>
                        )}
                        {evt.type === "agent_completed" && (
                          <>
                            <GitBranch
                              className="h-3.5 w-3.5 text-success"
                              aria-hidden="true"
                            />
                            <span className="text-success">
                              <span className="font-medium">{evt.agent}</span> finished
                            </span>
                          </>
                        )}
                        {evt.type === "started" && (
                          <>
                            <Loader2
                              className="h-3.5 w-3.5 animate-spin text-ink-muted"
                              aria-hidden="true"
                            />
                            <span className="text-ink-secondary">Agent started</span>
                          </>
                        )}
                      </div>
                    ))}
                    <div className="flex items-center gap-2 text-ink-secondary">
                      <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                      <span>Processing</span>
                    </div>
                  </>
                )}
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input bar */}
      <form
        onSubmit={handleSubmit}
        className="mt-3 flex items-end gap-2 rounded-card border border-line bg-surface p-2"
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything"
          aria-label="Message"
          rows={1}
          disabled={loading}
          className="max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-muted disabled:opacity-50"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={!input.trim() || loading}
          className={clsx(
            "shrink-0 rounded-control p-2.5 transition-colors duration-150",
            input.trim() && !loading
              ? "bg-accent text-white hover:bg-accent-hover"
              : "bg-surface-muted text-ink-muted"
          )}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </form>
    </div>
  );
}
