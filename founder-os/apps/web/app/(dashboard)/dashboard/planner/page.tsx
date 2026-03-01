"use client";

import { useState, useEffect, useCallback, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
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
  RotateCcw,
  Wrench,
  Plug,
  Zap,
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

/* ── Planner Page ─────────────────────────────────── */
export default function PlannerPage() {
  const api = useApi();
  const [status, setStatus] = useState<PlannerStatus | null>(null);
  const [history, setHistory] = useState<PlanHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);
  const [promptResult, setPromptResult] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [mcpTools, setMcpTools] = useState<MCPToolsStatus | null>(null);
  const [showMcpTools, setShowMcpTools] = useState(false);

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

  const handlePrompt = async (e: FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || sending) return;
    setSending(true);
    setPromptResult(null);
    try {
      const data = await api("/api/planner/prompt", {
        method: "POST",
        body: JSON.stringify({ message: prompt.trim() }),
      });
      setPromptResult(
        data.summary || data.content || data.message || "Plan updated successfully."
      );
      setPrompt("");
      fetchData(); // refresh status
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("Calendar not connected") || msg.includes("not connected")) {
        setPromptResult("Google Calendar not connected. Opening setup...");
        handleConnect();
        return;
      }
      setPromptResult(
        msg ? `Error: ${msg}` : "Something went wrong."
      );
    } finally {
      setSending(false);
    }
  };

  const handleGenerate = async () => {
    setSending(true);
    setPromptResult(null);
    setPromptResult("Generating your weekly plan… This may take 30-60 seconds.");
    try {
      const data = await api("/api/planner/generate", {
        method: "POST",
        body: JSON.stringify({ message: "Plan my week" }),
        direct: true,    // bypass Next.js proxy (this request takes 30-60s)
        timeoutMs: 120000, // 2 minute timeout
      });
      setPromptResult(
        data.message ||
          `Weekly plan generated! ${data.events_created ?? 0} events added to Google Calendar.`
      );
      fetchData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("Calendar not connected") || msg.includes("not connected")) {
        setPromptResult("Google Calendar not connected. Opening setup...");
        handleConnect();
        return;
      }
      // User-friendly error messages for common failures
      if (msg.includes("rate") || msg.includes("429") || msg.includes("Too Many")) {
        setPromptResult(
          "The AI service is temporarily rate-limited. Please wait a minute and try again."
        );
      } else if (msg.includes("Plan generation failed")) {
        setPromptResult(
          "Plan generation failed — the AI service may be temporarily unavailable. Retrying in a moment..."
        );
        // Auto-retry once after a short delay
        setTimeout(() => handleGenerate(), 5000);
      } else if (msg.includes("Calendar push failed")) {
        setPromptResult(
          "Plan was generated but couldn't be pushed to Google Calendar. Please check your calendar connection."
        );
      } else if (msg.includes("API error 5")) {
        setPromptResult(
          "Server error — please try again in a moment. If this persists, check the backend logs."
        );
      } else {
        setPromptResult(msg ? `Error: ${msg}` : "Generation failed. Please try again.");
      }
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Planner</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            AI-powered scheduling and calendar management
          </p>
        </div>
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
        </div>
      </div>
    );
  }

  const isOnboarded = status?.status !== "not_onboarded";
  const isGcalConnected = status?.gcal_connected === true;

  return (
    <div className="space-y-6">
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
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50"
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
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-6">
        <div className="flex items-center gap-3 mb-4">
          <div
            className={clsx(
              "w-3 h-3 rounded-full",
              status?.status === "active"
                ? "bg-emerald-500"
                : status?.status === "pending_gcal"
                ? "bg-amber-500"
                : "bg-gray-400"
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
            <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-4 h-4 text-indigo-500" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Primary Goal</span>
              </div>
              <p className="text-sm font-medium">{status?.primary_goal || "Not set"}</p>
            </div>
            <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <CalendarDays className="w-4 h-4 text-indigo-500" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Plans Generated</span>
              </div>
              <p className="text-sm font-medium">{status?.total_plans_generated ?? 0}</p>
            </div>
            <div className="p-4 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]">
              <div className="flex items-center gap-2 mb-2">
                <LinkIcon className="w-4 h-4 text-indigo-500" />
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Google Calendar</span>
              </div>
              <p className="text-sm font-medium">
                {isGcalConnected ? (
                  <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Connected
                  </span>
                ) : (
                  <button
                    onClick={handleConnect}
                    disabled={connecting}
                    className="text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1 text-sm"
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
          <div className="mt-4 p-4 rounded-xl bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                  Google Calendar not connected
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                  Connect your calendar to enable automatic scheduling and weekly plan generation.
                </p>
              </div>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="px-3 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 shrink-0"
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
              <Target className="w-4 h-4 text-indigo-500" />
              Goals This Week
            </h3>
            <ul className="space-y-1.5">
              {status.goals_this_week.map((goal, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 text-emerald-500 shrink-0" />
                  {goal}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Prompt Input */}
      {isOnboarded && (
        <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
          <h2 className="text-lg font-semibold mb-2">Plan with AI</h2>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            Tell the planner anything — schedule meetings, update goals, replan your week.
          </p>
          <form onSubmit={handlePrompt} className="flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Board meeting Friday at 2 PM, focus this week on fundraising..."
              disabled={sending}
              className="flex-1 px-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-indigo-400 disabled:opacity-50 placeholder:text-[var(--color-text-muted)]"
            />
            <button
              type="submit"
              disabled={!prompt.trim() || sending}
              className={clsx(
                "px-4 py-2.5 rounded-xl text-sm font-medium transition-colors",
                prompt.trim() && !sending
                  ? "bg-indigo-600 text-white hover:bg-indigo-700"
                  : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
              )}
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </form>
          {promptResult && (
            <div className="mt-3 p-3 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)] text-sm whitespace-pre-wrap">
              {promptResult}
            </div>
          )}
        </div>
      )}

      {/* MCP Tools Panel */}
      {isOnboarded && mcpTools && (
        <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
          <button
            onClick={() => setShowMcpTools(!showMcpTools)}
            className="flex items-center justify-between w-full"
          >
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Plug className="w-5 h-5 text-indigo-500" />
              MCP Tools
              <span className={clsx(
                "text-xs font-medium px-2 py-0.5 rounded-full",
                mcpTools.mcp_connected
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                  : "bg-gray-100 text-gray-500 dark:bg-gray-500/10 dark:text-gray-400"
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
                    "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border",
                    p.status === "connected"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-500/5 dark:border-emerald-500/20 dark:text-emerald-400"
                      : "bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-500/5 dark:border-amber-500/20 dark:text-amber-400"
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
                  className="p-3 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Plug className="w-4 h-4 text-indigo-500" />
                      <span className="text-sm font-semibold">
                        {p.name.replace("mcp:", "").replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}
                      </span>
                      <span className={clsx(
                        "text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wide",
                        p.status === "connected"
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                          : p.status === "token_expired"
                          ? "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400"
                          : "bg-gray-100 text-gray-500 dark:bg-gray-500/10 dark:text-gray-400"
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
                            <p className="text-xs font-mono font-medium text-indigo-600 dark:text-indigo-400 truncate">
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
        <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center justify-between w-full"
          >
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <History className="w-5 h-5 text-indigo-500" />
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
                  className="p-3 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
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
