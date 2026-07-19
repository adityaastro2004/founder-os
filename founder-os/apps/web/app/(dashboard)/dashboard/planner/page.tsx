"use client";

import { useState, useEffect, useCallback, useRef, FormEvent } from "react";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import { DIRECT_API_URL } from "@/lib/api";
import { useAuth } from "@clerk/nextjs";
import {
  ArrowRight,
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
import { PageHeader, Card, Button } from "@/app/_components/ui";

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

/* ── Planner page ─────────────────────────────────── */
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
        <PageHeader
          title="Planner"
          description="AI-powered scheduling and calendar management"
        />
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
        </div>
      </div>
    );
  }

  const isOnboarded = status?.status !== "not_onboarded";
  const isGcalConnected = status?.gcal_connected === true;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Planner"
        description="AI-powered scheduling and calendar management"
        actions={
          isOnboarded && isGcalConnected ? (
            <Button onClick={handleGenerate} loading={sending}>
              {!sending && <Sparkles className="h-4 w-4" aria-hidden="true" />}
              Generate weekly plan
            </Button>
          ) : undefined
        }
      />

      {/* Status card */}
      <Card className="p-6">
        <div className="mb-4 flex items-center gap-3">
          <div
            className={clsx(
              "h-3 w-3 rounded-full",
              status?.status === "active"
                ? "bg-success"
                : status?.status === "pending_gcal"
                  ? "bg-warning"
                  : "bg-ink-muted"
            )}
          />
          <h2 className="font-serif text-lg font-semibold text-ink">
            {status?.status === "active"
              ? "Planner active"
              : status?.status === "pending_gcal"
                ? "Calendar not connected"
                : "Setup required"}
          </h2>
        </div>

        {!isOnboarded ? (
          <div className="py-8 text-center">
            <CalendarDays
              className="mx-auto mb-3 h-10 w-10 text-ink-muted"
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <p className="mx-auto mb-4 max-w-md text-sm text-ink-secondary">
              The planner needs your business context before it can plan your
              week. Complete onboarding once and it activates automatically.
            </p>
            <Link
              href="/onboarding"
              className="inline-flex items-center gap-2 rounded-control bg-accent px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover"
            >
              Complete onboarding
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <p className="mt-3 text-xs text-ink-secondary">
              Already onboarded? Refresh this page — your profile syncs
              automatically.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-control border border-line bg-surface-muted/40 p-4">
              <div className="mb-2 flex items-center gap-2">
                <Target className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
                <span className="text-xs font-medium text-ink-secondary">Primary goal</span>
              </div>
              <p className="text-sm font-medium text-ink">{status?.primary_goal || "Not set"}</p>
            </div>
            <div className="rounded-control border border-line bg-surface-muted/40 p-4">
              <div className="mb-2 flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
                <span className="text-xs font-medium text-ink-secondary">Plans generated</span>
              </div>
              <p className="text-sm font-medium text-ink">{status?.total_plans_generated ?? 0}</p>
            </div>
            <div className="rounded-control border border-line bg-surface-muted/40 p-4">
              <div className="mb-2 flex items-center gap-2">
                <LinkIcon className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
                <span className="text-xs font-medium text-ink-secondary">Google Calendar</span>
              </div>
              <p className="text-sm font-medium">
                {isGcalConnected ? (
                  <span className="flex items-center gap-1 text-success">
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    Connected
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={handleConnect}
                    disabled={connecting}
                    className="flex items-center gap-1 text-sm text-ink-secondary hover:underline"
                  >
                    {connecting ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    {connecting ? "Connecting" : "Connect now"}
                  </button>
                )}
              </p>
            </div>
          </div>
        )}

        {/* GCal connect banner */}
        {isOnboarded && !isGcalConnected && (
          <div className="mt-4 rounded-control border border-warning/20 bg-warning-soft p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-ink">
                  Google Calendar not connected
                </p>
                <p className="mt-0.5 text-xs text-ink-secondary">
                  Connect your calendar to enable automatic scheduling and weekly plan generation.
                </p>
              </div>
              <button
                type="button"
                onClick={handleConnect}
                disabled={connecting}
                className="flex shrink-0 items-center gap-1.5 rounded-control bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors duration-150 hover:bg-accent-hover disabled:opacity-50"
              >
                {connecting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <LinkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {connecting ? "Opening" : "Connect Google Calendar"}
              </button>
            </div>
          </div>
        )}

        {/* Weekly goals */}
        {isOnboarded && status?.goals_this_week && status.goals_this_week.length > 0 && (
          <div className="mt-4 border-t border-line-subtle pt-4">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
              <Target className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
              Goals this week
            </h3>
            <ul className="space-y-1.5">
              {status.goals_this_week.map((goal, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-ink">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
                  {goal}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Chat interface */}
      {isOnboarded && (
        <Card className="p-5">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-serif text-lg font-semibold text-ink">
              <Bot className="h-5 w-5 text-ink-secondary" aria-hidden="true" />
              Plan with AI
            </h2>
            {chatMessages.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setChatMessages([]);
                  sessionIdRef.current = `planner-chat-${Date.now()}`;
                }}
                className="flex items-center gap-1 text-xs text-ink-secondary transition-colors duration-150 hover:text-ink"
              >
                <Trash2 className="h-3 w-3" aria-hidden="true" />
                Clear chat
              </button>
            )}
          </div>
          <p className="mb-4 text-xs text-ink-secondary">
            Ask anything — schedule meetings, delete events, update goals, replan your week.
            The AI will ask for details if needed.
          </p>

          {/* Chat messages */}
          {chatMessages.length > 0 && (
            <div className="mb-4 max-h-[400px] space-y-3 overflow-y-auto pr-1">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    "flex gap-2.5",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent">
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
                        {/* Tool badges */}
                        {msg.mcpToolsUsed && msg.mcpToolsUsed.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {msg.mcpToolsUsed.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary"
                              >
                                <Plug className="h-2.5 w-2.5" aria-hidden="true" />
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
            </div>
          )}

          <form onSubmit={handlePrompt} className="flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Delete all events this week, board meeting Friday at 2 PM"
              aria-label="Ask the planner"
              disabled={sending}
              className="flex-1 rounded-control border border-line bg-surface px-4 py-2.5 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-ink-muted focus:border-accent focus:ring-1 focus:ring-accent disabled:opacity-50"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={!prompt.trim() || sending}
              className={clsx(
                "rounded-control px-4 py-2.5 text-sm font-medium transition-colors duration-150",
                prompt.trim() && !sending
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
                  type="button"
                  onClick={() => setPrompt(suggestion)}
                  className="rounded-control border border-line px-3 py-1.5 text-xs text-ink-secondary transition-colors duration-150 hover:bg-surface-muted/60 hover:text-ink"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* MCP tools panel */}
      {isOnboarded && mcpTools && (
        <Card className="p-5">
          <button
            type="button"
            onClick={() => setShowMcpTools(!showMcpTools)}
            className="flex w-full items-center justify-between"
          >
            <h2 className="flex items-center gap-2 font-serif text-lg font-semibold text-ink">
              <Plug className="h-5 w-5 text-ink-secondary" aria-hidden="true" />
              MCP tools
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  mcpTools.mcp_connected
                    ? "bg-success-soft text-success"
                    : "bg-surface-muted text-ink-secondary"
                )}
              >
                {mcpTools.mcp_connected ? `${mcpTools.total_tools} tools active` : "Not connected"}
              </span>
            </h2>
            {showMcpTools ? (
              <ChevronUp className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            )}
          </button>

          {/* Collapsed summary */}
          {!showMcpTools && mcpTools.mcp_connected && (
            <div className="mt-3 flex flex-wrap gap-2">
              {mcpTools.providers.map((p) => (
                <span
                  key={p.name}
                  className={clsx(
                    "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs",
                    p.status === "connected"
                      ? "border-success/20 bg-success-soft text-success"
                      : "border-warning/20 bg-warning-soft text-warning"
                  )}
                >
                  <Zap className="h-3 w-3" aria-hidden="true" />
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
                  className="rounded-control border border-line bg-surface-muted/40 p-3"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Plug className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
                      <span className="text-sm font-semibold text-ink">
                        {p.name.replace("mcp:", "").replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}
                      </span>
                      <span
                        className={clsx(
                          "rounded px-1.5 py-0.5 text-[10px] font-medium",
                          p.status === "connected"
                            ? "bg-success-soft text-success"
                            : p.status === "token_expired"
                              ? "bg-danger-soft text-danger"
                              : "bg-surface-muted text-ink-secondary"
                        )}
                      >
                        {p.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-ink-secondary">
                      {p.type}
                    </span>
                  </div>

                  {/* Tools from this provider */}
                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {mcpTools.tools
                      .filter((t) => t.provider === p.name)
                      .map((tool) => (
                        <div
                          key={tool.name}
                          className="flex items-start gap-2 rounded-control px-2 py-1.5 transition-colors duration-150 hover:bg-surface"
                        >
                          <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
                          <div className="min-w-0">
                            <p className="truncate font-mono text-xs font-medium text-ink-secondary">
                              {tool.name}
                            </p>
                            <p className="line-clamp-1 text-[11px] text-ink-secondary">
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
                <div className="py-6 text-center">
                  <Plug className="mx-auto mb-2 h-8 w-8 text-ink-muted" aria-hidden="true" />
                  <p className="text-sm text-ink-secondary">
                    No MCP tools connected yet.
                  </p>
                  <p className="mt-1 text-xs text-ink-secondary">
                    Connect Google Calendar above to enable MCP calendar tools.
                  </p>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Plan history */}
      {history && history.total_plans > 0 && (
        <Card className="p-5">
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="flex w-full items-center justify-between"
          >
            <h2 className="flex items-center gap-2 font-serif text-lg font-semibold text-ink">
              <History className="h-5 w-5 text-ink-secondary" aria-hidden="true" />
              Plan history
              <span className="text-xs font-normal text-ink-secondary">
                ({history.total_plans})
              </span>
            </h2>
            {showHistory ? (
              <ChevronUp className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            )}
          </button>
          {showHistory && (
            <div className="mt-4 space-y-3">
              {history.plans.map((plan, i) => (
                <div
                  key={plan.id || i}
                  className="rounded-control border border-line bg-surface-muted/40 p-3"
                >
                  <div className="mb-1 flex items-center justify-between text-xs text-ink-secondary">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      {new Date(plan.created_at).toLocaleDateString("en-US", {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                    {plan.events_count != null && (
                      <span>{plan.events_count} events</span>
                    )}
                  </div>
                  <p className="text-sm text-ink">{plan.summary}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
