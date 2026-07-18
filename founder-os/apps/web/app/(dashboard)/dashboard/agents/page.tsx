"use client";

import { useState, useEffect, useRef, useCallback, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import { useEventSource } from "@/lib/use-event-source";
import { DIRECT_API_URL } from "@/lib/api";
import { useAuth } from "@clerk/nextjs";
import {
  Activity,
  Bot,
  CheckCircle2,
  XCircle,
  Wrench,
  GitBranch,
  Play,
  Pause,
  RefreshCw,
  Loader2,
  Wifi,
  WifiOff,
  ChevronDown,
  Filter,
  Clock,
  Zap,
  AlertTriangle,
  Send,
  X,
  ArrowLeft,
  Trash2,
  User,
  MessageSquare,
  History,
  ChevronRight,
} from "lucide-react";
import { clsx } from "clsx";
import { useChatStore, EMPTY_SESSION } from "@/lib/chat-store";

/* ── Types ───────────────────────────────────────────── */
interface ActivityEvent {
  id: string;
  event_type: string;
  agent_name: string;
  agent_display_name: string;
  title: string;
  description: string;
  status: string;
  metadata: Record<string, unknown>;
  timestamp: number;
  correlation_id: string;
}

interface AgentStatus {
  agent_name: string;
  display_name: string;
  status: "idle" | "running" | "error";
  last_active: number | null;
  tasks_today: number;
  tasks_completed: number;
  tasks_failed: number;
  avg_duration_seconds: number | null;
}

interface ActivityStats {
  agents: AgentStatus[];
  total_events_today: number;
  pending_approvals: number;
}

interface HistoryRun {
  id: string;
  agent_name: string;
  user_message: string;
  agent_response: string;
  model: string;
  tokens_used: number;
  cost_usd: number;
  duration_seconds: number;
  stop_reason: string;
  tool_names: string[];
  tool_calls_count: number;
  agents_used: string[];
  delegations_made: number;
  delegation_details: Record<string, unknown>[];
  status: string;
  created_at: string;
}

/* ── Agent colors ────────────────────────────────────── */
const agentColors: Record<string, string> = {
  orchestrator: "bg-neutral-900",
  planner: "bg-neutral-800",
  content: "bg-neutral-700",
  research: "bg-neutral-600",
  support: "bg-neutral-300",
  system: "bg-neutral-200",
};

const agentDescriptions: Record<string, string> = {
  orchestrator: "Routes tasks to the right specialist, monitors all agents",
  planner: "AI-powered scheduling, calendar management, weekly planning",
  content: "Blog posts, social media, marketing copy, newsletters",
  research: "Market research, competitor analysis, trend reports",
  support: "Customer support drafts, FAQ generation, ticket triage",
};

const agentSuggestions: Record<string, string[]> = {
  orchestrator: [
    "What did my agents do today?",
    "Summarize recent activity",
    "Which agent should handle investor outreach?",
    "Run a full status check on all systems",
  ],
  planner: [
    "What's on my calendar this week?",
    "Schedule a team standup tomorrow at 10 AM",
    "Plan my week focused on product launch",
    "Delete all events for this week",
  ],
  content: [
    "Write a blog post about AI for startups",
    "Draft a Twitter thread about our launch",
    "Create a newsletter for this week",
    "Write product announcement copy",
  ],
  research: [
    "Analyze competitors in the AI agent space",
    "What are the latest trends in SaaS?",
    "Research best pricing strategies for B2B",
    "Find market data on developer tools",
  ],
  support: [
    "Draft a response for a billing inquiry",
    "Generate FAQ for our new feature",
    "Triage these customer tickets",
    "Write a help article on getting started",
  ],
};

const statusIcons: Record<string, React.ElementType> = {
  started: Play,
  completed: CheckCircle2,
  failed: XCircle,
  tool_call: Wrench,
  delegation: GitBranch,
  info: Activity,
};

const statusColors: Record<string, string> = {
  started: "text-[var(--color-text-secondary)] bg-[var(--color-surface-muted)]",
  completed: "text-[var(--color-success)] bg-[var(--color-success)]/5",
  failed: "text-[var(--color-danger)] bg-[var(--color-danger)]/5",
  tool_call: "text-[var(--color-warning)] bg-[var(--color-warning)]/5",
  delegation: "text-[var(--color-text-secondary)] bg-[var(--color-surface-muted)]",
  info: "text-[var(--color-text-muted)] bg-[var(--color-surface-muted)]",
};

/* ── Time formatting ─────────────────────────────────── */
function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/* ── Agent Chat Panel (slide-over) ───────────────────── */
function AgentChatPanel({
  agent,
  onClose,
}: {
  agent: AgentStatus;
  onClose: () => void;
}) {
  const { sessions, ensureHistory, sendAgentChat, resetSession } = useChatStore();
  const [input, setInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [sessionId, setSessionId] = useState(() => {
    if (typeof window === "undefined") return `${agent.agent_name}-chat-${Date.now()}`;
    const key = `agent-chat-session-${agent.agent_name}`;
    const stored = localStorage.getItem(key);
    if (stored) return stored;
    const id = `${agent.agent_name}-chat-${Date.now()}`;
    localStorage.setItem(key, id);
    return id;
  });
  const gradient = agentColors[agent.agent_name] || agentColors.system;
  const suggestions = agentSuggestions[agent.agent_name] || [];

  // Chat state and the in-flight run live in ChatProvider (dashboard layout),
  // so closing this panel or switching tabs never interrupts a running agent.
  const session = sessions[sessionId] ?? EMPTY_SESSION;
  const messages = session.messages;
  const sending = session.pending;

  // Load persisted agent chat messages (once per session, provider-cached)
  useEffect(() => {
    ensureHistory(sessionId, agent.agent_name);
  }, [sessionId, agent.agent_name, ensureHistory]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = (text?: string) => {
    const userMessage = (text || input).trim();
    if (!userMessage || sending) return;
    setInput("");
    void sendAgentChat(agent.agent_name, sessionId, userMessage);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  const clearChat = () => {
    resetSession(sessionId);
    const newId = `${agent.agent_name}-chat-${Date.now()}`;
    if (typeof window !== "undefined") {
      localStorage.setItem(`agent-chat-session-${agent.agent_name}`, newId);
    }
    setSessionId(newId);
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <div className="relative ml-auto w-full max-w-2xl bg-white border-l border-[var(--color-border)] flex flex-col h-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[var(--color-border)]">
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
          >
            <ArrowLeft className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
          <div
            className={clsx(
              "w-8 h-8 rounded-md flex items-center justify-center",
              gradient
            )}
          >
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm">{agent.display_name}</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {agentDescriptions[agent.agent_name] || "AI Agent"}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={clsx(
                "w-1.5 h-1.5 rounded-full",
                agent.status === "running" &&
                  "bg-[var(--color-success)] animate-pulse",
                agent.status === "idle" && "bg-[var(--color-text-muted)]",
                agent.status === "error" && "bg-[var(--color-danger)]"
              )}
            />
            <span className="text-xs text-[var(--color-text-muted)] capitalize">
              {agent.status}
            </span>
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
              title="Clear chat"
            >
              <Trash2 className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
          >
            <X className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full">
              <div
                className={clsx(
                  "w-14 h-14 rounded-lg flex items-center justify-center mb-4",
                  gradient
                )}
              >
                <Bot className="w-7 h-7 text-white" />
              </div>
              <h2 className="text-lg font-semibold mb-1">
                Chat with {agent.display_name}
              </h2>
              <p className="text-sm text-[var(--color-text-secondary)] max-w-sm text-center mb-6">
                {agentDescriptions[agent.agent_name] ||
                  "Ask this agent anything."}
              </p>
              {suggestions.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSend(s)}
                      className="flex items-center gap-3 p-3 rounded-lg border border-[var(--color-border-subtle)] bg-white hover:bg-[var(--color-surface-subtle)] transition-colors text-left"
                    >
                      <MessageSquare className="w-4 h-4 text-[var(--color-text-muted)] shrink-0" />
                      <span className="text-sm">{s}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    "flex gap-2.5",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div
                      className={clsx(
                        "w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5",
                        gradient
                      )}
                    >
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                  )}
                  <div
                    className={clsx(
                      "max-w-[80%] rounded-lg px-4 py-2.5 text-sm",
                      msg.role === "user"
                        ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] rounded-br-sm"
                        : msg.status === "error"
                        ? "bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20 text-[var(--color-danger)] rounded-bl-sm"
                        : msg.status === "clarification"
                        ? "bg-[var(--color-warning)]/5 border border-[var(--color-warning)]/20 rounded-bl-sm"
                        : msg.status === "sending"
                        ? "bg-[var(--color-surface-subtle)] border border-[var(--color-border)] rounded-bl-sm"
                        : "bg-[var(--color-surface-subtle)] border border-[var(--color-border)] rounded-bl-sm"
                    )}
                  >
                    {msg.status === "sending" ? (
                      <div className="flex items-center gap-2 text-[var(--color-text-muted)]">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Thinking...</span>
                      </div>
                    ) : (
                      <>
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                        {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {msg.toolsUsed.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-mono"
                              >
                                <Wrench className="w-2.5 h-2.5" />
                                {tool}
                              </span>
                            ))}
                          </div>
                        )}
                        {msg.durationSeconds && msg.role === "assistant" && (
                          <div className="mt-1.5 text-[10px] text-[var(--color-text-muted)]">
                            {msg.durationSeconds.toFixed(1)}s
                            {msg.tokensUsed
                              ? ` \u00b7 ${msg.tokensUsed} tokens`
                              : ""}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-7 h-7 rounded-md bg-[var(--color-surface-muted)] flex items-center justify-center shrink-0 mt-0.5">
                      <User className="w-4 h-4 text-[var(--color-text-secondary)]" />
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--color-border)] p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask ${agent.display_name} anything...`}
              disabled={sending}
              className="flex-1 px-4 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] disabled:opacity-50 placeholder:text-[var(--color-text-muted)]"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className={clsx(
                "px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
                input.trim() && !sending
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent-hover)]"
                  : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
              )}
            >
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ── Agent History Panel (slide-over) ────────────────── */
function AgentHistoryPanel({
  agent,
  onClose,
}: {
  agent: AgentStatus;
  onClose: () => void;
}) {
  const { getToken } = useAuth();
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const gradient = agentColors[agent.agent_name] || agentColors.system;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(
          `${DIRECT_API_URL}/api/history/runs?agent_name=${encodeURIComponent(agent.agent_name)}&limit=50`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} }
        );
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data)) setRuns(data);
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [agent.agent_name, getToken]);

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-2xl bg-white border-l border-[var(--color-border)] flex flex-col h-full shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[var(--color-border)]">
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors">
            <ArrowLeft className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
          <div className={clsx("w-8 h-8 rounded-md flex items-center justify-center", gradient)}>
            <History className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm">{agent.display_name} — History</p>
            <p className="text-xs text-[var(--color-text-muted)]">Past runs with full input & output</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors">
            <X className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
        </div>

        {/* Runs list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
            </div>
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <History className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
              <h3 className="text-lg font-semibold mb-1">No history yet</h3>
              <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
                Run tasks with this agent and they&apos;ll appear here.
              </p>
            </div>
          ) : (
            runs.map((run) => {
              const isExpanded = expandedId === run.id;
              return (
                <div key={run.id} className="bg-[var(--color-surface-subtle)] border border-[var(--color-border)] rounded-lg overflow-hidden">
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : run.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-surface-muted)] transition-colors"
                  >
                    <ChevronRight className={clsx("w-4 h-4 text-[var(--color-text-muted)] transition-transform shrink-0", isExpanded && "rotate-90")} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{run.user_message}</p>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[var(--color-text-muted)]">
                        <span>{new Date(run.created_at).toLocaleString()}</span>
                        <span>·</span>
                        <span>{run.duration_seconds.toFixed(1)}s</span>
                        <span>·</span>
                        <span>{run.tokens_used} tokens</span>
                        {run.tool_names.length > 0 && (
                          <>
                            <span>·</span>
                            <span className="flex items-center gap-0.5"><Wrench className="w-2.5 h-2.5" />{run.tool_calls_count}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <span className={clsx(
                      "text-[10px] px-2 py-0.5 rounded-full font-medium",
                      run.status === "completed" ? "bg-[var(--color-success)]/10 text-[var(--color-success)]" : "bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
                    )}>
                      {run.status}
                    </span>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-[var(--color-border)] px-4 py-3 space-y-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase text-[var(--color-text-muted)] mb-1">You said</p>
                        <div className="text-sm bg-white rounded-lg border border-[var(--color-border)] px-3 py-2 whitespace-pre-wrap">
                          {run.user_message}
                        </div>
                      </div>
                      <div>
                        <p className="text-[10px] font-semibold uppercase text-[var(--color-text-muted)] mb-1">Agent response</p>
                        <div className="text-sm bg-white rounded-lg border border-[var(--color-border)] px-3 py-2 whitespace-pre-wrap max-h-80 overflow-y-auto">
                          {run.agent_response}
                        </div>
                      </div>
                      {run.tool_names.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {run.tool_names.map((t) => (
                            <span key={t} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-mono">
                              <Wrench className="w-2.5 h-2.5" />{t}
                            </span>
                          ))}
                        </div>
                      )}
                      {run.agents_used && run.agents_used.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {run.agents_used.map((a) => (
                            <span key={a} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
                              <GitBranch className="w-2.5 h-2.5" />{a}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-[var(--color-text-muted)]">
                        <span>Model: {run.model}</span>
                        {run.cost_usd > 0 && <span>Cost: ${run.cost_usd.toFixed(4)}</span>}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Agent Status Card ───────────────────────────────── */
function AgentStatusCard({
  agent,
  onClick,
  onHistory,
}: {
  agent: AgentStatus;
  onClick: () => void;
  onHistory: () => void;
}) {
  const gradient = agentColors[agent.agent_name] || agentColors.system;
  return (
    <div
      className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-4 hover:bg-[var(--color-surface-subtle)] hover:border-[var(--color-border)] transition-all text-left w-full group"
    >
      <button onClick={onClick} className="w-full text-left">
        <div className="flex items-center gap-3 mb-3">
          <div
            className={clsx(
              "w-8 h-8 rounded-md flex items-center justify-center",
              gradient
            )}
          >
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">{agent.display_name}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className={clsx(
                  "w-1.5 h-1.5 rounded-full",
                  agent.status === "running" &&
                    "bg-[var(--color-success)] animate-pulse",
                  agent.status === "idle" && "bg-[var(--color-text-muted)]",
                  agent.status === "error" && "bg-[var(--color-danger)]"
                )}
              />
              <span className="text-xs text-[var(--color-text-muted)] capitalize">
                {agent.status}
              </span>
            </div>
          </div>
          <MessageSquare className="w-4 h-4 text-[var(--color-text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <p className="text-xs text-[var(--color-text-secondary)] mb-3 line-clamp-1">
          {agentDescriptions[agent.agent_name] || "AI Agent"}
        </p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-base font-semibold tabular-nums">
              {agent.tasks_today}
            </p>
            <p className="text-[10px] text-[var(--color-text-muted)]">Today</p>
          </div>
          <div>
            <p className="text-base font-semibold tabular-nums text-[var(--color-success)]">
              {agent.tasks_completed}
            </p>
            <p className="text-[10px] text-[var(--color-text-muted)]">Done</p>
          </div>
          <div>
            <p className="text-base font-semibold tabular-nums text-[var(--color-danger)]">
              {agent.tasks_failed}
            </p>
            <p className="text-[10px] text-[var(--color-text-muted)]">Failed</p>
          </div>
        </div>
      </button>
      <div className="flex items-center justify-between mt-2">
        {agent.last_active ? (
          <p className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
            <Clock className="w-3 h-3" />
            Last active {timeAgo(agent.last_active)}
          </p>
        ) : <span />}
        <button
          onClick={(e) => { e.stopPropagation(); onHistory(); }}
          className="inline-flex items-center gap-1 text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors px-2 py-1 rounded hover:bg-[var(--color-surface-muted)]"
        >
          <History className="w-3 h-3" />
          History
        </button>
      </div>
    </div>
  );
}

/* ── Activity Event Row ──────────────────────────────── */
function EventRow({
  event,
  isNew,
}: {
  event: ActivityEvent;
  isNew: boolean;
}) {
  const Icon = statusIcons[event.status] || Activity;
  const colorClass = statusColors[event.status] || statusColors.info;
  const gradient = agentColors[event.agent_name] || agentColors.system;

  return (
    <div
      className={clsx(
        "flex items-start gap-3 py-3 px-4 rounded-xl transition-all duration-500",
        isNew && "bg-[var(--color-surface-muted)]"
      )}
    >
      <div
        className={clsx(
          "w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5",
          gradient
        )}
      >
        <Bot className="w-3.5 h-3.5 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate">{event.title}</p>
          <span
            className={clsx(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium",
              colorClass
            )}
          >
            <Icon className="w-3 h-3" />
            {event.status}
          </span>
        </div>
        {event.description && (
          <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 line-clamp-2">
            {event.description}
          </p>
        )}
        {typeof event.metadata?.tool_name === "string" && (
          <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-md bg-[var(--color-surface-muted)] text-[10px] font-mono text-[var(--color-text-secondary)]">
            <Wrench className="w-3 h-3" />
            {event.metadata.tool_name}
          </span>
        )}
      </div>
      <span className="text-[10px] text-[var(--color-text-muted)] whitespace-nowrap shrink-0 mt-1">
        {timeAgo(event.timestamp)}
      </span>
    </div>
  );
}

/* ── Main Page ───────────────────────────────────────── */
export default function AgentsPage() {
  const api = useApi();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [paused, setPaused] = useState(false);
  const [filterAgent, setFilterAgent] = useState<string>("");
  const [newEventIds, setNewEventIds] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  // Agent chat panel state
  const [chatAgent, setChatAgent] = useState<AgentStatus | null>(null);
  const [historyAgent, setHistoryAgent] = useState<AgentStatus | null>(null);

  /* ── SSE: Real-time event stream ── */
  const { connected } = useEventSource<ActivityEvent>(
    `${DIRECT_API_URL}/api/activity/stream`,
    {
      enabled: !paused,
      onEvent: (event) => {
        setEvents((prev) => {
          const exists = prev.some((e) => e.id === event.id);
          if (exists) return prev;
          setNewEventIds((ids) => new Set([...ids, event.id]));
          setTimeout(
            () =>
              setNewEventIds((ids) => {
                const next = new Set(ids);
                next.delete(event.id);
                return next;
              }),
            3000
          );
          return [event, ...prev].slice(0, 200);
        });
      },
    }
  );

  /* ── Fetch initial data ── */
  const fetchData = useCallback(async () => {
    try {
      const [recentData, statsData] = await Promise.all([
        api("/api/activity/recent?limit=50").catch(() => ({ events: [] })),
        api("/api/activity/stats").catch(() => null),
      ]);
      setEvents(recentData.events || []);
      if (statsData) setStats(statsData);
    } catch {
      // API might not be ready yet
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Polling for stats (every 10s) ── */
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const statsData = await api("/api/activity/stats");
        if (statsData) setStats(statsData);
      } catch {
        // ignore
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [api]);

  /* ── Filtered events ── */
  const filteredEvents = filterAgent
    ? events.filter((e) => e.agent_name === filterAgent)
    : events;

  const agentNames = [
    ...new Set(events.map((e) => e.agent_name).filter(Boolean)),
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Click any agent to start a conversation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border",
              connected
                ? "text-[var(--color-success)] border-[var(--color-success)]/20 bg-[var(--color-success)]/5"
                : paused
                ? "text-[var(--color-text-muted)] border-[var(--color-border)] bg-[var(--color-surface-muted)]"
                : "text-[var(--color-warning)] border-[var(--color-warning)]/20 bg-[var(--color-warning)]/5"
            )}
          >
            {connected ? (
              <Wifi className="w-3.5 h-3.5" />
            ) : (
              <WifiOff className="w-3.5 h-3.5" />
            )}
            {connected ? "Live" : paused ? "Paused" : "Connecting..."}
          </span>

          <button
            onClick={() => setPaused(!paused)}
            className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
            title={paused ? "Resume" : "Pause"}
          >
            {paused ? (
              <Play className="w-4 h-4 text-[var(--color-text-secondary)]" />
            ) : (
              <Pause className="w-4 h-4 text-[var(--color-text-secondary)]" />
            )}
          </button>

          <button
            onClick={fetchData}
            className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xl font-semibold tabular-nums">
                {stats.total_events_today}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">
                Events today
              </p>
            </div>
          </div>
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xl font-semibold tabular-nums">
                {stats.agents.filter((a) => a.status === "running").length}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">
                Active agents
              </p>
            </div>
          </div>
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xl font-semibold tabular-nums">
                {stats.pending_approvals}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">
                Pending approvals
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Agent Cards */}
      {stats && stats.agents.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-3">
            Your Agents
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {stats.agents.map((agent) => (
              <AgentStatusCard
                key={agent.agent_name}
                agent={agent}
                onClick={() => setChatAgent(agent)}
                onHistory={() => setHistoryAgent(agent)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Event Feed */}
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <Activity className="w-4 h-4 text-[var(--color-text-secondary)]" />
            Event Feed
            {filteredEvents.length > 0 && (
              <span className="text-xs text-[var(--color-text-muted)] font-normal">
                ({filteredEvents.length} events)
              </span>
            )}
          </h2>
          <div className="relative">
            <select
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              className="appearance-none text-xs pl-7 pr-6 py-1.5 rounded-lg border border-[var(--color-border)] bg-white text-[var(--color-text)] cursor-pointer hover:border-[var(--color-text-muted)] transition-colors"
            >
              <option value="">All agents</option>
              {agentNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <Filter className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-text-muted)]" />
            <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-text-muted)]" />
          </div>
        </div>
        <div
          ref={scrollRef}
          className="divide-y divide-[var(--color-border)] max-h-[50vh] sm:max-h-[600px] overflow-y-auto"
        >
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
              <span className="ml-2 text-sm text-[var(--color-text-secondary)]">
                Loading activity...
              </span>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Activity className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
              <h3 className="text-lg font-semibold mb-1">No activity yet</h3>
              <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
                Agent events will appear here in real-time as your agents work.
                Click an agent above to start a conversation.
              </p>
            </div>
          ) : (
            filteredEvents.map((event, idx) => (
              <EventRow
                key={event.id ? `${event.id}` : `evt-${idx}`}
                event={event}
                isNew={newEventIds.has(event.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Agent Chat Panel */}
      {chatAgent && (
        <AgentChatPanel
          agent={chatAgent}
          onClose={() => setChatAgent(null)}
        />
      )}

      {/* Agent History Panel */}
      {historyAgent && (
        <AgentHistoryPanel
          agent={historyAgent}
          onClose={() => setHistoryAgent(null)}
        />
      )}
    </div>
  );
}
