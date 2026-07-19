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
import { PageHeader, Card, Badge } from "@/app/_components/ui";

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
  orchestrator: "bg-ink",
  planner: "bg-ink-secondary",
  content: "bg-accent",
  research: "bg-success",
  support: "bg-warning",
  system: "bg-ink-muted",
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
  started: "text-ink-secondary bg-surface-muted",
  completed: "text-success bg-success-soft",
  failed: "text-danger bg-danger-soft",
  tool_call: "text-warning bg-warning-soft",
  delegation: "text-ink-secondary bg-surface-muted",
  info: "text-ink-secondary bg-surface-muted",
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

/* ── Status dot ──────────────────────────────────────── */
function StatusDot({ status }: { status: AgentStatus["status"] }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={clsx(
          "h-1.5 w-1.5 rounded-full",
          status === "running" && "animate-pulse bg-success",
          status === "idle" && "bg-ink-muted",
          status === "error" && "bg-danger"
        )}
      />
      <span className="text-xs capitalize text-ink-secondary">{status}</span>
    </span>
  );
}

/* ── Agent chat panel (slide-over) ───────────────────── */
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
  const accentBg = agentColors[agent.agent_name] || agentColors.system;
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
        className="absolute inset-0 bg-ink/20 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <div className="relative ml-auto flex h-full w-full max-w-2xl flex-col border-l border-line bg-surface shadow-xl">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            aria-label="Back"
            className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
          >
            <ArrowLeft className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </button>
          <div
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-md",
              accentBg
            )}
          >
            <Bot className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">{agent.display_name}</p>
            <p className="text-xs text-ink-secondary">
              {agentDescriptions[agent.agent_name] || "AI agent"}
            </p>
          </div>
          <StatusDot status={agent.status} />
          {messages.length > 0 && (
            <button
              type="button"
              onClick={clearChat}
              className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
              title="Clear chat"
              aria-label="Clear chat"
            >
              <Trash2 className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
          >
            <X className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center">
              <div
                className={clsx(
                  "mb-4 flex h-14 w-14 items-center justify-center rounded-card",
                  accentBg
                )}
              >
                <Bot className="h-7 w-7 text-white" aria-hidden="true" />
              </div>
              <h2 className="mb-1 font-serif text-lg font-semibold text-ink">
                Chat with {agent.display_name}
              </h2>
              <p className="mb-6 max-w-sm text-center text-sm text-ink-secondary">
                {agentDescriptions[agent.agent_name] || "Ask this agent anything."}
              </p>
              {suggestions.length > 0 && (
                <div className="grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => handleSend(s)}
                      className="flex items-center gap-3 rounded-card border border-line bg-surface p-3 text-left transition-colors duration-150 hover:bg-surface-muted/50"
                    >
                      <MessageSquare
                        className="h-4 w-4 shrink-0 text-ink-muted"
                        aria-hidden="true"
                      />
                      <span className="text-sm text-ink">{s}</span>
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
                        "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                        accentBg
                      )}
                    >
                      <Bot className="h-4 w-4 text-white" aria-hidden="true" />
                    </div>
                  )}
                  <div
                    className={clsx(
                      "max-w-[80%] rounded-card px-4 py-2.5 text-sm",
                      msg.role === "user"
                        ? "rounded-br-md bg-surface-muted text-ink"
                        : msg.status === "error"
                          ? "rounded-bl-md border border-danger/20 bg-danger-soft text-danger"
                          : msg.status === "clarification"
                            ? "rounded-bl-md border border-warning/20 bg-warning-soft text-ink"
                            : "rounded-bl-md border border-line bg-paper text-ink"
                    )}
                  >
                    {msg.status === "sending" ? (
                      <div className="flex items-center gap-2 text-ink-secondary">
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        <span>Thinking</span>
                      </div>
                    ) : (
                      <>
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                        {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {msg.toolsUsed.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary"
                              >
                                <Wrench className="h-2.5 w-2.5" aria-hidden="true" />
                                {tool}
                              </span>
                            ))}
                          </div>
                        )}
                        {msg.durationSeconds && msg.role === "assistant" && (
                          <div className="mt-1.5 text-[10px] text-ink-secondary">
                            {msg.durationSeconds.toFixed(1)}s
                            {msg.tokensUsed ? ` · ${msg.tokensUsed} tokens` : ""}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-muted">
                      <User className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-line p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask ${agent.display_name} anything`}
              aria-label={`Message ${agent.display_name}`}
              disabled={sending}
              className="flex-1 rounded-control border border-line bg-surface px-4 py-2.5 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-muted focus:border-accent focus:ring-1 focus:ring-accent disabled:opacity-50"
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={!input.trim() || sending}
              className={clsx(
                "rounded-control px-4 py-2.5 text-sm font-medium transition-colors duration-150",
                input.trim() && !sending
                  ? "bg-accent text-white hover:bg-accent-hover"
                  : "bg-surface-muted text-ink-muted"
              )}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Send className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* ── Agent history panel (slide-over) ────────────────── */
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
  const accentBg = agentColors[agent.agent_name] || agentColors.system;

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
      <div className="absolute inset-0 bg-ink/20 backdrop-blur-sm" onClick={onClose} />
      <div className="relative ml-auto flex h-full w-full max-w-2xl flex-col border-l border-line bg-surface shadow-xl">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            aria-label="Back"
            className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
          >
            <ArrowLeft className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </button>
          <div className={clsx("flex h-8 w-8 items-center justify-center rounded-md", accentBg)}>
            <History className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">{agent.display_name} — history</p>
            <p className="text-xs text-ink-secondary">Past runs with full input and output</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
          >
            <X className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </button>
        </div>

        {/* Runs list */}
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
            </div>
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <History className="mb-4 h-10 w-10 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
              <h3 className="mb-1 font-serif text-lg font-semibold text-ink">No history yet</h3>
              <p className="max-w-sm text-sm text-ink-secondary">
                Run tasks with this agent and they&apos;ll appear here.
              </p>
            </div>
          ) : (
            runs.map((run) => {
              const isExpanded = expandedId === run.id;
              return (
                <div key={run.id} className="overflow-hidden rounded-card border border-line bg-paper">
                  <button
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : run.id)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-surface-muted/50"
                  >
                    <ChevronRight
                      className={clsx(
                        "h-4 w-4 shrink-0 text-ink-muted transition-transform duration-150",
                        isExpanded && "rotate-90"
                      )}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{run.user_message}</p>
                      <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-secondary">
                        <span>{new Date(run.created_at).toLocaleString()}</span>
                        <span>·</span>
                        <span>{run.duration_seconds.toFixed(1)}s</span>
                        <span>·</span>
                        <span>{run.tokens_used} tokens</span>
                        {run.tool_names.length > 0 && (
                          <>
                            <span>·</span>
                            <span className="flex items-center gap-0.5">
                              <Wrench className="h-2.5 w-2.5" aria-hidden="true" />
                              {run.tool_calls_count}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <Badge tone={run.status === "completed" ? "success" : "danger"}>
                      {run.status}
                    </Badge>
                  </button>
                  {isExpanded && (
                    <div className="space-y-3 border-t border-line px-4 py-3">
                      <div>
                        <p className="mb-1 text-[10px] font-semibold text-ink-secondary">You said</p>
                        <div className="whitespace-pre-wrap rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink">
                          {run.user_message}
                        </div>
                      </div>
                      <div>
                        <p className="mb-1 text-[10px] font-semibold text-ink-secondary">Agent response</p>
                        <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink">
                          {run.agent_response}
                        </div>
                      </div>
                      {run.tool_names.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {run.tool_names.map((t) => (
                            <span key={t} className="inline-flex items-center gap-1 rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
                              <Wrench className="h-2.5 w-2.5" aria-hidden="true" />
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                      {run.agents_used && run.agents_used.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {run.agents_used.map((a) => (
                            <span key={a} className="inline-flex items-center gap-1 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-secondary">
                              <GitBranch className="h-2.5 w-2.5" aria-hidden="true" />
                              {a}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] text-ink-secondary">
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

/* ── Agent status card ───────────────────────────────── */
function AgentStatusCard({
  agent,
  onClick,
  onHistory,
}: {
  agent: AgentStatus;
  onClick: () => void;
  onHistory: () => void;
}) {
  const accentBg = agentColors[agent.agent_name] || agentColors.system;
  return (
    <Card className="group w-full p-4 text-left transition-colors duration-150 hover:bg-surface-muted/40">
      <button type="button" onClick={onClick} className="w-full text-left">
        <div className="mb-3 flex items-center gap-3">
          <div
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-md",
              accentBg
            )}
          >
            <Bot className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{agent.display_name}</p>
            <div className="mt-0.5">
              <StatusDot status={agent.status} />
            </div>
          </div>
          <MessageSquare
            className="h-4 w-4 text-ink-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100"
            aria-hidden="true"
          />
        </div>
        <p className="mb-3 line-clamp-1 text-xs text-ink-secondary">
          {agentDescriptions[agent.agent_name] || "AI agent"}
        </p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-base font-semibold tabular-nums text-ink">
              {agent.tasks_today}
            </p>
            <p className="text-[10px] text-ink-secondary">Today</p>
          </div>
          <div>
            <p className="text-base font-semibold tabular-nums text-success">
              {agent.tasks_completed}
            </p>
            <p className="text-[10px] text-ink-secondary">Done</p>
          </div>
          <div>
            <p className="text-base font-semibold tabular-nums text-danger">
              {agent.tasks_failed}
            </p>
            <p className="text-[10px] text-ink-secondary">Failed</p>
          </div>
        </div>
      </button>
      <div className="mt-2 flex items-center justify-between">
        {agent.last_active ? (
          <p className="flex items-center gap-1 text-[10px] text-ink-secondary">
            <Clock className="h-3 w-3" aria-hidden="true" />
            Last active {timeAgo(agent.last_active)}
          </p>
        ) : <span />}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onHistory(); }}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] text-ink-secondary transition-colors duration-150 hover:bg-surface-muted hover:text-ink"
        >
          <History className="h-3 w-3" aria-hidden="true" />
          History
        </button>
      </div>
    </Card>
  );
}

/* ── Activity event row ──────────────────────────────── */
function EventRow({
  event,
  isNew,
}: {
  event: ActivityEvent;
  isNew: boolean;
}) {
  const Icon = statusIcons[event.status] || Activity;
  const colorClass = statusColors[event.status] || statusColors.info;
  const accentBg = agentColors[event.agent_name] || agentColors.system;

  return (
    <div
      className={clsx(
        "flex items-start gap-3 px-4 py-3 transition-colors duration-500",
        isNew && "bg-surface-muted"
      )}
    >
      <div
        className={clsx(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
          accentBg
        )}
      >
        <Bot className="h-3.5 w-3.5 text-white" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-ink">{event.title}</p>
          <span
            className={clsx(
              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium",
              colorClass
            )}
          >
            <Icon className="h-3 w-3" aria-hidden="true" />
            {event.status}
          </span>
        </div>
        {event.description && (
          <p className="mt-0.5 line-clamp-2 text-xs text-ink-secondary">
            {event.description}
          </p>
        )}
        {typeof event.metadata?.tool_name === "string" && (
          <span className="mt-1 inline-flex items-center gap-1 rounded-md bg-surface-muted px-2 py-0.5 font-mono text-[10px] text-ink-secondary">
            <Wrench className="h-3 w-3" aria-hidden="true" />
            {event.metadata.tool_name}
          </span>
        )}
      </div>
      <span className="mt-1 shrink-0 whitespace-nowrap text-[10px] text-ink-secondary">
        {timeAgo(event.timestamp)}
      </span>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────── */
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

  /* ── SSE: real-time event stream ── */
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
      <PageHeader
        title="Agents"
        description="Click any agent to start a conversation"
        actions={
          <>
            <span
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-control border px-3 py-1.5 text-xs font-medium",
                connected
                  ? "border-success/20 bg-success-soft text-success"
                  : paused
                    ? "border-line bg-surface-muted text-ink-secondary"
                    : "border-warning/20 bg-warning-soft text-warning"
              )}
            >
              {connected ? (
                <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {connected ? "Live" : paused ? "Paused" : "Connecting"}
            </span>

            <button
              type="button"
              onClick={() => setPaused(!paused)}
              className="rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted"
              title={paused ? "Resume" : "Pause"}
              aria-label={paused ? "Resume stream" : "Pause stream"}
            >
              {paused ? (
                <Play className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
              ) : (
                <Pause className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
              )}
            </button>

            <button
              type="button"
              onClick={fetchData}
              className="rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted"
              title="Refresh"
              aria-label="Refresh"
            >
              <RefreshCw className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
            </button>
          </>
        }
      />

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            { icon: Activity, value: stats.total_events_today, label: "Events today" },
            {
              icon: Zap,
              value: stats.agents.filter((a) => a.status === "running").length,
              label: "Active agents",
            },
            { icon: AlertTriangle, value: stats.pending_approvals, label: "Pending approvals" },
          ].map((s) => (
            <Card key={s.label} className="flex items-center gap-3 p-4">
              <div className="rounded-md bg-surface-muted p-2 text-ink-secondary">
                <s.icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <div>
                <p className="text-xl font-semibold tabular-nums text-ink">{s.value}</p>
                <p className="text-xs text-ink-secondary">{s.label}</p>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Agent cards */}
      {stats && stats.agents.length > 0 && (
        <div>
          <h2 className="mb-3 text-[13px] font-medium text-ink-secondary">
            Your agents
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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

      {/* Event feed */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Activity className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
            Event feed
            {filteredEvents.length > 0 && (
              <span className="text-xs font-normal text-ink-secondary">
                ({filteredEvents.length} events)
              </span>
            )}
          </h2>
          <div className="relative">
            <select
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              aria-label="Filter by agent"
              className="cursor-pointer appearance-none rounded-control border border-line bg-surface py-1.5 pl-7 pr-6 text-xs text-ink transition-colors duration-150 hover:border-ink-muted"
            >
              <option value="">All agents</option>
              {agentNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <Filter
              className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
              aria-hidden="true"
            />
            <ChevronDown
              className="absolute right-1.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
              aria-hidden="true"
            />
          </div>
        </div>
        <div
          ref={scrollRef}
          className="max-h-[50vh] divide-y divide-line-subtle overflow-y-auto sm:max-h-[600px]"
        >
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
              <span className="ml-2 text-sm text-ink-secondary">
                Loading activity
              </span>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Activity className="mb-4 h-10 w-10 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
              <h3 className="mb-1 font-serif text-lg font-semibold text-ink">No activity yet</h3>
              <p className="max-w-sm text-sm text-ink-secondary">
                Agent events will appear here in real time as your agents work.
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
      </Card>

      {/* Agent chat panel */}
      {chatAgent && (
        <AgentChatPanel
          agent={chatAgent}
          onClose={() => setChatAgent(null)}
        />
      )}

      {/* Agent history panel */}
      {historyAgent && (
        <AgentHistoryPanel
          agent={historyAgent}
          onClose={() => setHistoryAgent(null)}
        />
      )}
    </div>
  );
}
