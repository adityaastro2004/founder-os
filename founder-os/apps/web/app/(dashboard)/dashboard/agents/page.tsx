"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "@/lib/use-api";
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
} from "lucide-react";
import { clsx } from "clsx";

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

/* ── Agent colors & icons ────────────────────────────── */
const agentColors: Record<string, string> = {
  orchestrator: "from-violet-500 to-purple-600",
  planner: "from-blue-500 to-indigo-600",
  content: "from-pink-500 to-rose-600",
  research: "from-emerald-500 to-teal-600",
  ops: "from-amber-500 to-orange-600",
  product: "from-cyan-500 to-blue-600",
  support: "from-lime-500 to-green-600",
  system: "from-gray-500 to-slate-600",
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
  started: "text-blue-500 bg-blue-500/10",
  completed: "text-emerald-500 bg-emerald-500/10",
  failed: "text-red-500 bg-red-500/10",
  tool_call: "text-amber-500 bg-amber-500/10",
  delegation: "text-purple-500 bg-purple-500/10",
  info: "text-gray-500 bg-gray-500/10",
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

/* ── Agent Status Badge ──────────────────────────────── */
function AgentStatusCard({ agent }: { agent: AgentStatus }) {
  const gradient = agentColors[agent.agent_name] || agentColors.system;
  return (
    <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3 mb-3">
        <div
          className={clsx(
            "w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center",
            gradient
          )}
        >
          <Bot className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{agent.display_name}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className={clsx(
                "w-2 h-2 rounded-full",
                agent.status === "running" && "bg-emerald-500 animate-pulse",
                agent.status === "idle" && "bg-gray-400",
                agent.status === "error" && "bg-red-500"
              )}
            />
            <span className="text-xs text-[var(--color-text-secondary)] capitalize">
              {agent.status}
            </span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-lg font-bold">{agent.tasks_today}</p>
          <p className="text-[10px] text-[var(--color-text-muted)]">Today</p>
        </div>
        <div>
          <p className="text-lg font-bold text-emerald-600">{agent.tasks_completed}</p>
          <p className="text-[10px] text-[var(--color-text-muted)]">Done</p>
        </div>
        <div>
          <p className="text-lg font-bold text-red-500">{agent.tasks_failed}</p>
          <p className="text-[10px] text-[var(--color-text-muted)]">Failed</p>
        </div>
      </div>
      {agent.last_active && (
        <p className="text-[10px] text-[var(--color-text-muted)] mt-2 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Last active {timeAgo(agent.last_active)}
        </p>
      )}
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
        isNew && "bg-indigo-50/50 dark:bg-indigo-500/5"
      )}
    >
      {/* Agent avatar */}
      <div
        className={clsx(
          "w-8 h-8 rounded-lg bg-gradient-to-br flex items-center justify-center shrink-0 mt-0.5",
          gradient
        )}
      >
        <Bot className="w-4 h-4 text-white" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium truncate">{event.title}</p>
          <span className={clsx("inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium", colorClass)}>
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

      {/* Timestamp */}
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

  /* ── Polling for new events (every 3s) ── */
  useEffect(() => {
    if (paused) return;

    const interval = setInterval(async () => {
      try {
        const data = await api("/api/activity/recent?limit=10");
        if (data.events?.length) {
          setEvents((prev) => {
            const existingIds = new Set(prev.map((e) => e.id));
            const newOnes = data.events.filter(
              (e: ActivityEvent) => !existingIds.has(e.id)
            );
            if (newOnes.length > 0) {
              setNewEventIds(new Set(newOnes.map((e: ActivityEvent) => e.id)));
              setTimeout(() => setNewEventIds(new Set()), 3000);
              return [...newOnes, ...prev].slice(0, 200);
            }
            return prev;
          });
        }
      } catch {
        // ignore
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [api, paused]);

  /* ── Filtered events ── */
  const filteredEvents = filterAgent
    ? events.filter((e) => e.agent_name === filterAgent)
    : events;

  const agentNames = [
    ...new Set(events.map((e) => e.agent_name).filter(Boolean)),
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Activity</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Real-time agent status and event feed
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Connection status */}
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
              !paused
                ? "text-emerald-700 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-500/10"
                : "text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-500/10"
            )}
          >
            {!paused ? (
              <Wifi className="w-3.5 h-3.5" />
            ) : (
              <WifiOff className="w-3.5 h-3.5" />
            )}
            {!paused ? "Live" : "Paused"}
          </span>

          {/* Pause/resume */}
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

          {/* Refresh */}
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
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.total_events_today}</p>
              <p className="text-xs text-[var(--color-text-secondary)]">Events today</p>
            </div>
          </div>
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {stats.agents.filter((a) => a.status === "running").length}
              </p>
              <p className="text-xs text-[var(--color-text-secondary)]">Active agents</p>
            </div>
          </div>
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-4 flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.pending_approvals}</p>
              <p className="text-xs text-[var(--color-text-secondary)]">Pending approvals</p>
            </div>
          </div>
        </div>
      )}

      {/* Agent Status Cards */}
      {stats && stats.agents.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-3">
            Agent Status
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {stats.agents.map((agent) => (
              <AgentStatusCard key={agent.agent_name} agent={agent} />
            ))}
          </div>
        </div>
      )}

      {/* Event Feed */}
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] overflow-hidden">
        {/* Feed header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-500" />
            Event Feed
            {filteredEvents.length > 0 && (
              <span className="text-xs text-[var(--color-text-muted)] font-normal">
                ({filteredEvents.length} events)
              </span>
            )}
          </h2>

          {/* Agent filter */}
          <div className="relative">
            <select
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              className="appearance-none text-xs pl-7 pr-6 py-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-primary)] cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500/30 transition-colors"
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

        {/* Event list */}
        <div
          ref={scrollRef}
          className="divide-y divide-[var(--color-border)] max-h-[600px] overflow-y-auto"
        >
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
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
                Try running an agent from the chat or orchestrator.
              </p>
            </div>
          ) : (
            filteredEvents.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                isNew={newEventIds.has(event.id)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
