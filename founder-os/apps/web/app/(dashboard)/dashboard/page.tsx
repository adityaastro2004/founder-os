"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import { useEventSource } from "@/lib/use-event-source";
import {
  Bot,
  CalendarDays,
  Brain,
  ListTodo,
  Zap,
  TrendingUp,

  CheckCircle2,
  ArrowRight,
  Sparkles,
  Activity,
  AlertTriangle,
  Loader2,
  XCircle,
  Wrench,
  GitBranch,
  Play,
  Eye,
} from "lucide-react";
import Link from "next/link";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface AgentStatus {
  agent_name: string;
  display_name: string;
  status: "idle" | "running" | "error";
  last_active: number | null;
  tasks_today: number;
  tasks_completed: number;
  tasks_failed: number;
}

interface ActivityStats {
  agents: AgentStatus[];
  total_events_today: number;
  pending_approvals: number;
}

interface ReviewStats {
  pending_review: number;
  approved_today: number;
  rejected_today: number;
  edited_today: number;
  total_tasks: number;
  avg_rating: number | null;
}

interface MemoryStats {
  total_memories: number;
  chapters: number;
  pinned: number;
}

interface KnowledgeStats {
  total_items: number;
  total_chunks: number;
  categories: Record<string, number>;
}

interface ActivityEvent {
  id: string;
  event_type: string;
  agent_name: string;
  agent_display_name: string;
  title: string;
  description: string;
  status: string;
  timestamp: number;
}

/* ── Stat Card ─────────────────────────────────────── */
function StatCard({
  label,
  value,
  change,
  icon: Icon,
  color,
  loading,
}: {
  label: string;
  value: string;
  change: string;
  icon: React.ElementType;
  color: string;
  loading?: boolean;
}) {
  return (
    <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--color-text-secondary)]">{label}</p>
          {loading ? (
            <div className="h-8 w-12 mt-1 rounded bg-[var(--color-surface-muted)] animate-pulse" />
          ) : (
            <p className="text-2xl font-bold mt-1 tracking-tight">{value}</p>
          )}
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" />
            {change}
          </p>
        </div>
        <div className={`p-2.5 rounded-xl ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}

/* ── Activity Item ────────────────────────────────── */
const statusIconMap: Record<string, React.ElementType> = {
  started: Play,
  completed: CheckCircle2,
  failed: XCircle,
  tool_call: Wrench,
  delegation: GitBranch,
  info: Activity,
};

const statusColorMap: Record<string, string> = {
  started: "bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400",
  completed: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
  failed: "bg-red-100 text-red-600 dark:bg-red-500/10 dark:text-red-400",
  tool_call: "bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400",
  delegation: "bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400",
  info: "bg-gray-100 text-gray-600 dark:bg-gray-500/10 dark:text-gray-400",
};

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function ActivityItem({ event }: { event: ActivityEvent }) {
  const Icon = statusIconMap[event.status] || Activity;
  const color = statusColorMap[event.status] || statusColorMap.info;
  return (
    <div className="flex items-start gap-3 py-3">
      <div className={`p-2 rounded-lg shrink-0 ${color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{event.title}</p>
        {event.description && (
          <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 line-clamp-1">
            {event.description}
          </p>
        )}
      </div>
      <span className="text-xs text-[var(--color-text-muted)] whitespace-nowrap">
        {timeAgo(event.timestamp)}
      </span>
    </div>
  );
}

/* ── Quick Action Card ────────────────────────────── */
function QuickAction({
  title,
  description,
  href,
  icon: Icon,
  color,
}: {
  title: string;
  description: string;
  href: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-4 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-indigo-300 dark:hover:border-indigo-500/30 hover:shadow-md transition-all"
    >
      <div className={`p-2.5 rounded-xl ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1">
        <p className="font-medium text-sm">{title}</p>
        <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
          {description}
        </p>
      </div>
      <ArrowRight className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-indigo-500 group-hover:translate-x-0.5 transition-all" />
    </Link>
  );
}

/* ── Active Agent Row ─────────────────────────────── */
function AgentRow({ agent }: { agent: AgentStatus }) {
  const statusStyles = {
    running:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    idle: "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    error:
      "bg-red-100 text-red-600 dark:bg-red-500/10 dark:text-red-400",
  };

  return (
    <div className="flex items-center gap-3 py-3">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{agent.display_name}</p>
        <p className="text-xs text-[var(--color-text-secondary)] truncate">
          {agent.tasks_today} tasks today · {agent.tasks_completed} done
        </p>
      </div>
      <span
        className={clsx(
          "px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full",
          statusStyles[agent.status] || statusStyles.idle
        )}
      >
        {agent.status}
      </span>
    </div>
  );
}

/* ── Dashboard Page ───────────────────────────────── */
export default function DashboardPage() {
  const api = useApi();
  const [activityStats, setActivityStats] = useState<ActivityStats | null>(null);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [knowledgeStats, setKnowledgeStats] = useState<KnowledgeStats | null>(null);
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);

  /* ── SSE: real-time activity events ── */
  useEventSource<ActivityEvent>("/api/activity/stream", {
    onEvent: (event) => {
      if (event.event_type === "connected" || !event.title) return;
      setRecentEvents((prev) => [event, ...prev].slice(0, 10));
    },
  });

  /* ── Initial data load ── */
  const fetchData = useCallback(async () => {
    try {
      const [activity, review, memory, knowledge, recent] = await Promise.all([
        api("/api/activity/stats").catch(() => null),
        api("/api/review/stats").catch(() => null),
        api("/api/memory/stats").catch(() => null),
        api("/api/knowledge/stats").catch(() => null),
        api("/api/activity/recent?limit=10").catch(() => ({ events: [] })),
      ]);
      if (activity) setActivityStats(activity);
      if (review) setReviewStats(review);
      if (memory) setMemoryStats(memory);
      if (knowledge) setKnowledgeStats(knowledge);
      if (recent.events?.length) setRecentEvents(recent.events);
    } catch {
      // API not ready
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Periodic refresh (30s) ── */
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  /* ── Computed stats ── */
  const activeAgents = activityStats?.agents.filter((a) => a.status === "running").length ?? 0;
  const totalAgents = activityStats?.agents.length ?? 0;
  const tasksCompleted = reviewStats?.approved_today ?? 0;
  const pendingReview = reviewStats?.pending_review ?? 0;
  const memoryCount = memoryStats?.total_memories ?? 0;
  const knowledgeCount = knowledgeStats?.total_items ?? 0;

  return (
    <div className="space-y-8">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back 👋
        </h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Here&apos;s what&apos;s happening with your AI operating system today.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Agents"
          value={`${activeAgents}/${totalAgents}`}
          change={`${activityStats?.total_events_today ?? 0} events today`}
          icon={Bot}
          color="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
          loading={loading}
        />
        <StatCard
          label="Tasks Completed"
          value={String(tasksCompleted)}
          change={`${pendingReview} pending review`}
          icon={CheckCircle2}
          color="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
          loading={loading}
        />
        <StatCard
          label="Pending Approvals"
          value={String(activityStats?.pending_approvals ?? 0)}
          change={`${reviewStats?.rejected_today ?? 0} rejected today`}
          icon={AlertTriangle}
          color="bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
          loading={loading}
        />
        <StatCard
          label="Memory Entries"
          value={String(memoryCount)}
          change={`${knowledgeCount} knowledge items`}
          icon={Brain}
          color="bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400"
          loading={loading}
        />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column (2/3) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Actions */}
          <div>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-500" />
              Quick Actions
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <QuickAction
                title="Chat with Agents"
                description="Ask anything — auto-delegates to specialists"
                href="/dashboard/chat"
                icon={Bot}
                color="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
              />
              <QuickAction
                title="Review Tasks"
                description={pendingReview > 0 ? `${pendingReview} tasks need review` : "Approve agent outputs"}
                href="/dashboard/tasks"
                icon={ListTodo}
                color="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
              />
              <QuickAction
                title="Weekly Planner"
                description="AI-powered schedule optimization"
                href="/dashboard/planner"
                icon={CalendarDays}
                color="bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
              />
              <QuickAction
                title="Knowledge Base"
                description={knowledgeCount > 0 ? `${knowledgeCount} items indexed` : "Upload docs for agents"}
                href="/dashboard/knowledge"
                icon={Zap}
                color="bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400"
              />
            </div>
          </div>

          {/* Recent Activity — live via SSE */}
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-semibold">Recent Activity</h2>
              <Link
                href="/dashboard/agents"
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                View all
              </Link>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mb-4">
              Live updates from your agents
            </p>
            <div className="divide-y divide-[var(--color-border)]">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                  <span className="ml-2 text-sm text-[var(--color-text-secondary)]">Loading activity...</span>
                </div>
              ) : recentEvents.length === 0 ? (
                <div className="py-8 text-center">
                  <Activity className="w-8 h-8 text-[var(--color-text-muted)] mx-auto mb-2" />
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    No activity yet. Run an agent from the Chat page to get started.
                  </p>
                </div>
              ) : (
                recentEvents.slice(0, 5).map((event) => (
                  <ActivityItem key={event.id} event={event} />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right column (1/3) */}
        <div className="space-y-6">
          {/* Active Agents */}
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Active Agents</h2>
              <Link
                href="/dashboard/agents"
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                View all
              </Link>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                </div>
              ) : activityStats?.agents && activityStats.agents.length > 0 ? (
                activityStats.agents.slice(0, 5).map((agent) => (
                  <AgentRow key={agent.agent_name} agent={agent} />
                ))
              ) : (
                <div className="py-8 text-center">
                  <Bot className="w-8 h-8 text-[var(--color-text-muted)] mx-auto mb-2" />
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    No agents registered yet.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Review Queue */}
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Review Queue</h2>
              <Link
                href="/dashboard/tasks"
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                View all
              </Link>
            </div>
            <div className="space-y-3">
              {[
                {
                  label: "Pending Review",
                  value: reviewStats?.pending_review ?? 0,
                  icon: Eye,
                  color: "text-amber-500",
                },
                {
                  label: "Approved Today",
                  value: reviewStats?.approved_today ?? 0,
                  icon: CheckCircle2,
                  color: "text-emerald-500",
                },
                {
                  label: "Rejected Today",
                  value: reviewStats?.rejected_today ?? 0,
                  icon: XCircle,
                  color: "text-red-500",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-3 p-3 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <item.icon className={clsx("w-4 h-4", item.color)} />
                  <span className="text-sm flex-1">{item.label}</span>
                  <span className="text-sm font-bold">{loading ? "—" : item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
