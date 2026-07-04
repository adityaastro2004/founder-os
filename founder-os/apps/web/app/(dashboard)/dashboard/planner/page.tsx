"use client";

import { useState, useEffect, useCallback, useRef, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import { DIRECT_API_URL } from "@/lib/api";
import { useAuth } from "@clerk/nextjs";
import {
  CalendarDays,
  Send,
  Loader2,
  CheckCircle2,
  Target,
  Clock,
  AlertCircle,
  LinkIcon,
  History,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Plus,
  Wrench,
  Plug,
  Zap,
  Bot,
  User,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface PlannerStatus {
  status: "not_onboarded" | "pending_gcal" | "active";
  message: string;
  user_id?: string;
  business_name?: string;
  gcal_connected?: boolean;
  timezone?: string;
  goals_this_week?: string[];
  primary_goal?: string;
  last_plan_at?: string | null;
  last_plan_events?: number | null;
  total_plans_generated?: number;
}

interface PlanHistory {
  user_id: string;
  total_plans: number;
  plans: Array<{
    id?: string;
    created_at: string;
    summary: string;
    events_count?: number;
    prompt?: string;
  }>;
}

interface MCPToolInfo {
  name: string;
  description: string;
  provider: string;
}

interface MCPProvider {
  name: string;
  type: string;
  status: string;
  tool_count: number;
}

interface MCPToolsStatus {
  user_id: string;
  mcp_connected: boolean;
  providers: MCPProvider[];
  tools: MCPToolInfo[];
  total_tools: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  toolsUsed?: string[];
  mcpToolsUsed?: string[];
  tokensUsed?: number;
  durationSeconds?: number;
  status?: "sending" | "completed" | "error" | "clarification";
}

/* ── Planner Page ─────────────────────────────────── */
export default function PlannerPage() {
  const api = useApi();
  const { getToken } = useAuth();
  const [status, setStatus] = useState<PlannerStatus | null>(null);
  const [history, setHistory] = useState<PlanHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [mcpTools, setMcpTools] = useState<MCPToolsStatus | null>(null);
  const [showMcpTools, setShowMcpTools] = useState(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const hasRetriedRef = useRef(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string>(`planner-chat-${Date.now()}`);

  const fetchData = useCallback(async () => {
    try {
      const [s, h, m] = await Promise.all([
        api("/api/planner/status").catch(() => null),
        api("/api/planner/history?limit=5").catch(() => null),
        api("/api/planner/mcp-tools").catch(() => null),
      ]);
      if (s) setStatus(s);
      if (h) setHistory(h);
      if (m) setMcpTools(m);
    } catch {
      // backend not ready
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleConnect = useCallback(async () => {
    setConnecting(true);
    try {
      const data = await api("/api/planner/connect");
      if (data.status === "already_connected") {
        fetchData();
        return;
      }
      if (data.auth_url) {
        const popup = window.open(
          data.auth_url,
          "gcal-connect",
          "width=600,height=700,popup=yes"
        );
        if (popup) {
          const timer = setInterval(() => {
            if (popup.closed) {
              clearInterval(timer);
              setConnecting(false);
              fetchData();
            }
          }, 500);
        } else {
          // Popup blocked — fall back to redirect
          window.location.href = data.auth_url;
        }
        return;
      }
    } catch {
      // ignore
    } finally {
      setConnecting(false);
    }
  }, [api, fetchData]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handlePrompt = async (e: FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || sending) return;
    const userMessage = prompt.trim();
    setSending(true);
    setPrompt("");

    // Add user message to chat
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: userMessage,
      timestamp: new Date(),
    };
    setChatMessages((prev) => [...prev, userMsg]);

    // Add placeholder assistant message
    const assistantId = `assistant-${Date.now()}`;
    const pendingMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      status: "sending",
    };
    setChatMessages((prev) => [...prev, pendingMsg]);

    try {
      // Use the agent-based /api/planner/chat endpoint (MCP-powered)
      const token = await getToken();
      const res = await fetch(`${DIRECT_API_URL}/api/planner/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionIdRef.current,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API error ${res.status}`);
      }

      const data = await res.json();

      // If Google Calendar auth expired, show reconnect prompt
      if (data.reconnect_required) {
        setChatMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content:
                    "Your Google Calendar connection has expired. Reconnecting now...",
                  status: "error" as const,
                }
              : m
          )
        );
        handleConnect();
        setSending(false);
        return;
      }

      // Update the assistant message with the response
      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: data.reply || data.content || "Done.",
                status: data.status === "clarification_needed" ? "clarification" : "completed",
                toolsUsed: data.tool_names || [],
                mcpToolsUsed: data.mcp_tools_used || [],
                tokensUsed: data.tokens_used,
                durationSeconds: data.duration_seconds,
              }
            : m
        )
      );
      fetchData(); // refresh status
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (
        msg.includes("Calendar not connected") ||
        msg.includes("not connected") ||
        msg.includes("authorization expired") ||
        msg.includes("reconnect")
      ) {
        setChatMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Google Calendar connection expired. Reconnecting...", status: "error" }
              : m
          )
        );
        handleConnect();
        setSending(false);
        return;
      }
      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: msg || "Something went wrong.", status: "error" }
            : m
        )
      );
    } finally {
      setSending(false);
    }
  };

  const handleGenerate = async () => {
    setSending(true);

    // Add a user message for the generate action
    const userMsg: ChatMessage = {
      id: `user-gen-${Date.now()}`,
      role: "user",
      content: "Generate my weekly plan",
      timestamp: new Date(),
    };
    const assistantId = `assistant-gen-${Date.now()}`;
    const pendingMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "Generating your weekly plan… This may take 30-60 seconds.",
      timestamp: new Date(),
      status: "sending",
    };
    setChatMessages((prev) => [...prev, userMsg, pendingMsg]);

    try {
      const data = await api("/api/planner/generate", {
        method: "POST",
        body: JSON.stringify({ message: "Plan my week" }),
        direct: true,    // bypass Next.js proxy (this request takes 30-60s)
        timeoutMs: 120000, // 2 minute timeout
      });

      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: data.message || `Weekly plan generated! ${data.events_created ?? 0} events added to Google Calendar.`,
                status: "completed" as const,
              }
            : m
        )
      );
      hasRetriedRef.current = false;
      fetchData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (
        msg.includes("Calendar not connected") ||
        msg.includes("not connected") ||
        msg.includes("authorization expired") ||
        msg.includes("reconnect")
      ) {
        setChatMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Google Calendar connection expired. Reconnecting...", status: "error" as const }
              : m
          )
        );
        handleConnect();
        setSending(false);
        return;
      }

      let errorMsg = msg || "Generation failed. Please try again.";
      if (msg.includes("rate") || msg.includes("429") || msg.includes("Too Many")) {
        errorMsg = "The AI service is temporarily rate-limited. Please wait a minute and try again.";
      } else if (msg.includes("Plan generation failed") && !hasRetriedRef.current) {
        errorMsg = "Plan generation failed — retrying once...";
        hasRetriedRef.current = true;
        setChatMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: errorMsg, status: "sending" as const } : m
          )
        );
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
        retryTimerRef.current = setTimeout(() => handleGenerate(), 5000);
        return;
      } else if (msg.includes("Calendar push failed")) {
        errorMsg = "Plan was generated but couldn't be pushed to Google Calendar. Check your calendar connection.";
      } else if (msg.includes("API error 5")) {
        errorMsg = "Server error — please try again in a moment.";
      }

      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: errorMsg, status: "error" as const } : m
        )
      );
      hasRetriedRef.current = false;
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Planner</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            AI-powered scheduling and calendar management
          </p>
        </div>
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </div>
    );
  }

  const isOnboarded = status?.status !== "not_onboarded";
  const isGcalConnected = status?.gcal_connected === true;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Planner</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            AI-powered scheduling and calendar management
          </p>
        </div>
        {isOnboarded && isGcalConnected && (
          <button
            onClick={handleGenerate}
            disabled={sending}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-accent)] text-[var(--color-accent-foreground)] text-sm font-medium rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
          >
            {sending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            Generate Weekly Plan
          </button>
        )}
      </div>

      {/* Status Card */}
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-6">
        <div className="flex items-center gap-3 mb-4">
          <div
            className={clsx(
              "w-3 h-3 rounded-full",
              status?.status === "active"
                ? "bg-[var(--color-success)]"
                : status?.status === "pending_gcal"
                ? "bg-[var(--color-warning)]"
                : "bg-[var(--color-text-muted)]"
            )}
          />
          <h2 className="text-lg font-semibold">
            {status?.status === "active"
              ? "Planner Active"
              : status?.status === "pending_gcal"
              ? "Calendar Not Connected"
              : "Setup Required"}
          </h2>
        </div>

        {!isOnboarded ? (
          <div className="text-center py-8">
            <CalendarDays className="w-12 h-12 text-[var(--color-text-muted)] mx-auto mb-3" />
            <p className="text-sm text-[var(--color-text-secondary)] max-w-md mx-auto mb-4">
              {status?.message || "Set up your business context to get started with AI planning."}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              Complete onboarding to activate the planner.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-4 h-4 text-[var(--color-text-secondary)]" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Primary Goal</span>
              </div>
              <p className="text-sm font-medium">{status?.primary_goal || "Not set"}</p>
            </div>
            <div className="p-4 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <CalendarDays className="w-4 h-4 text-[var(--color-text-secondary)]" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Plans Generated</span>
              </div>
              <p className="text-sm font-medium">{status?.total_plans_generated ?? 0}</p>
            </div>
            <div className="p-4 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <LinkIcon className="w-4 h-4 text-[var(--color-text-secondary)]" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Google Calendar</span>
              </div>
              <p className="text-sm font-medium">
                {isGcalConnected ? (
                  <span className="text-[var(--color-success)] flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Connected
                  </span>
                ) : (
                  <button
                    onClick={handleConnect}
                    disabled={connecting}
                    className="text-[var(--color-text-secondary)] hover:underline flex items-center gap-1 text-sm"
                  >
                    {connecting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Plus className="w-3.5 h-3.5" />
                    )}
                    {connecting ? "Connecting..." : "Connect now"}
                  </button>
                )}
              </p>
            </div>
          </div>
        )}

        {/* GCal Connect Banner */}
        {isOnboarded && !isGcalConnected && (
          <div className="mt-4 p-4 rounded-lg bg-[var(--color-warning)]/5 border border-[var(--color-warning)]/20">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-[var(--color-warning)] shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium">
                  Google Calendar not connected
                </p>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                  Connect your calendar to enable automatic scheduling and weekly plan generation.
                </p>
              </div>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="px-3 py-1.5 text-xs font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 shrink-0"
              >
                {connecting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <LinkIcon className="w-3.5 h-3.5" />
                )}
                {connecting ? "Opening..." : "Connect Google Calendar"}
              </button>
            </div>
          </div>
        )}

        {/* Weekly Goals */}
        {isOnboarded && status?.goals_this_week && status.goals_this_week.length > 0 && (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
            <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
              <Target className="w-4 h-4 text-[var(--color-text-secondary)]" />
              Goals This Week
            </h3>
            <ul className="space-y-1.5">
              {status.goals_this_week.map((goal, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 text-[var(--color-success)] shrink-0" />
                  {goal}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Chat Interface */}
      {isOnboarded && (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Bot className="w-5 h-5 text-[var(--color-text-secondary)]" />
              Plan with AI
            </h2>
            {chatMessages.length > 0 && (
              <button
                onClick={() => {
                  setChatMessages([]);
                  sessionIdRef.current = `planner-chat-${Date.now()}`;
                }}
                className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] flex items-center gap-1 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Clear chat
              </button>
            )}
          </div>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            Ask anything — schedule meetings, delete events, update goals, replan your week.
            The AI will ask for details if needed.
          </p>

          {/* Chat Messages */}
          {chatMessages.length > 0 && (
            <div className="mb-4 max-h-[400px] overflow-y-auto space-y-3 pr-1">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    "flex gap-2.5",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="w-7 h-7 rounded-md bg-[var(--color-accent)] flex items-center justify-center shrink-0 mt-0.5">
                      <Bot className="w-4 h-4 text-[var(--color-accent-foreground)]" />
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
                        {/* Tool badges */}
                        {msg.mcpToolsUsed && msg.mcpToolsUsed.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {msg.mcpToolsUsed.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-mono"
                              >
                                <Plug className="w-2.5 h-2.5" />
                                {tool}
                              </span>
                            ))}
                          </div>
                        )}
                        {msg.durationSeconds && msg.role === "assistant" && (
                          <div className="mt-1.5 text-[10px] text-[var(--color-text-muted)]">
                            {msg.durationSeconds.toFixed(1)}s
                            {msg.tokensUsed ? ` · ${msg.tokensUsed} tokens` : ""}
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
            </div>
          )}

          <form onSubmit={handlePrompt} className="flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Delete all events this week, Board meeting Friday at 2 PM..."
              disabled={sending}
              className="flex-1 px-4 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] disabled:opacity-50 placeholder:text-[var(--color-text-muted)]"
            />
            <button
              type="submit"
              disabled={!prompt.trim() || sending}
              className={clsx(
                "px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
                prompt.trim() && !sending
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent-hover)]"
                  : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
              )}
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </form>

          {/* Suggested prompts */}
          {chatMessages.length === 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                "What's on my calendar this week?",
                "Delete all events for this week",
                "Schedule a team standup tomorrow at 10 AM",
                "Plan my week focused on product launch",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setPrompt(suggestion)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)] transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* MCP Tools Panel */}
      {isOnboarded && mcpTools && (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
          <button
            onClick={() => setShowMcpTools(!showMcpTools)}
            className="flex items-center justify-between w-full"
          >
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Plug className="w-5 h-5 text-[var(--color-text-secondary)]" />
              MCP Tools
              <span className={clsx(
                "text-xs font-medium px-2 py-0.5 rounded-full",
                mcpTools.mcp_connected
                  ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                  : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
              )}>
                {mcpTools.mcp_connected ? `${mcpTools.total_tools} tools active` : "Not connected"}
              </span>
            </h2>
            {showMcpTools ? (
              <ChevronUp className="w-4 h-4 text-[var(--color-text-muted)]" />
            ) : (
              <ChevronDown className="w-4 h-4 text-[var(--color-text-muted)]" />
            )}
          </button>

          {/* Collapsed summary */}
          {!showMcpTools && mcpTools.mcp_connected && (
            <div className="mt-3 flex flex-wrap gap-2">
              {mcpTools.providers.map((p) => (
                <span
                  key={p.name}
                  className={clsx(
                    "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border",
                    p.status === "connected"
                      ? "bg-[var(--color-success)]/5 border-[var(--color-success)]/20 text-[var(--color-success)]"
                      : "bg-[var(--color-warning)]/5 border-[var(--color-warning)]/20 text-[var(--color-warning)]"
                  )}
                >
                  <Zap className="w-3 h-3" />
                  {p.name.replace("mcp:", "")} — {p.tool_count} tools
                </span>
              ))}
            </div>
          )}

          {/* Expanded tool list */}
          {showMcpTools && (
            <div className="mt-4 space-y-3">
              {/* Providers */}
              {mcpTools.providers.map((p) => (
                <div
                  key={p.name}
                  className="p-3 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Plug className="w-4 h-4 text-[var(--color-text-secondary)]" />
                      <span className="text-sm font-semibold">
                        {p.name.replace("mcp:", "").replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}
                      </span>
                      <span className={clsx(
                        "text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wide",
                        p.status === "connected"
                          ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                          : p.status === "token_expired"
                          ? "bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
                          : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
                      )}>
                        {p.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wide">
                      {p.type}
                    </span>
                  </div>

                  {/* Tools from this provider */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                    {mcpTools.tools
                      .filter((t) => t.provider === p.name)
                      .map((tool) => (
                        <div
                          key={tool.name}
                          className="flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--color-surface)] transition-colors"
                        >
                          <Wrench className="w-3.5 h-3.5 text-[var(--color-text-muted)] mt-0.5 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-xs font-mono font-medium text-[var(--color-text-secondary)] truncate">
                              {tool.name}
                            </p>
                            <p className="text-[11px] text-[var(--color-text-muted)] line-clamp-1">
                              {tool.description}
                            </p>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              ))}

              {/* No providers */}
              {mcpTools.providers.length === 0 && (
                <div className="text-center py-6">
                  <Plug className="w-8 h-8 text-[var(--color-text-muted)] mx-auto mb-2" />
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    No MCP tools connected yet.
                  </p>
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">
                    Connect Google Calendar above to enable MCP calendar tools.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Plan History */}
      {history && history.total_plans > 0 && (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center justify-between w-full"
          >
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <History className="w-5 h-5 text-[var(--color-text-secondary)]" />
              Plan History
              <span className="text-xs font-normal text-[var(--color-text-muted)]">
                ({history.total_plans})
              </span>
            </h2>
            {showHistory ? (
              <ChevronUp className="w-4 h-4 text-[var(--color-text-muted)]" />
            ) : (
              <ChevronDown className="w-4 h-4 text-[var(--color-text-muted)]" />
            )}
          </button>
          {showHistory && (
            <div className="mt-4 space-y-3">
              {history.plans.map((plan, i) => (
                <div
                  key={plan.id || i}
                  className="p-3 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-[var(--color-text-muted)] flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(plan.created_at).toLocaleDateString("en-US", {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                    {plan.events_count != null && (
                      <span className="text-xs text-[var(--color-text-muted)]">
                        {plan.events_count} events
                      </span>
                    )}
                  </div>
                  <p className="text-sm">{plan.summary}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
