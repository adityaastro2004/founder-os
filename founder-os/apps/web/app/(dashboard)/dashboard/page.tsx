"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import { useEventSource } from "@/lib/use-event-source";
import {
  Bot,
  CalendarDays,
  Brain,
  ListTodo,

  CheckCircle2,
  ArrowRight,
  Activity,
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
  sub,
  loading,
}: {
  label: string;
  value: string;
  sub: string;
  loading?: boolean;
}) {
  return (
    <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-4">
      <p className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider font-medium">{label}</p>
      {loading ? (
        <div className="h-7 w-10 mt-1.5 rounded bg-[var(--color-surface-muted)] animate-pulse" />
      ) : (
        <p className="text-2xl font-semibold mt-1 tracking-tight">{value}</p>
      )}
      <p className="text-xs text-[var(--color-text-secondary)] mt-1">{sub}</p>
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
  return (
    <div className="flex items-start gap-3 py-3">
      <div className="p-1.5 rounded-md bg-[var(--color-surface-muted)] shrink-0">
        <Icon className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate">{event.title}</p>
        {event.description && (
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5 line-clamp-1">
            {event.description}
          </p>
        )}
      </div>
      <span className="text-[11px] text-[var(--color-text-muted)] whitespace-nowrap">
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
}: {
  title: string;
  description: string;
  href: string;
  icon: React.ElementType;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 p-3.5 rounded-lg border border-[var(--color-border-subtle)] bg-white hover:bg-[var(--color-surface-subtle)] transition-colors"
    >
      <div className="p-2 rounded-md bg-[var(--color-surface-muted)] group-hover:bg-[var(--color-surface)]">
        <Icon className="w-4 h-4 text-[var(--color-text-secondary)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          {description}
        </p>
      </div>
      <ArrowRight className="w-3.5 h-3.5 text-[var(--color-text-muted)] group-hover:translate-x-0.5 transition-transform" />
    </Link>
  );
}

/* ── Agent Row ─────────────────────────────────────── */
function AgentRow({ agent }: { agent: AgentStatus }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="w-7 h-7 rounded-md bg-[var(--color-surface-muted)] flex items-center justify-center shrink-0">
        <Bot className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate">{agent.display_name}</p>
        <p className="text-[11px] text-[var(--color-text-muted)]">
          {agent.tasks_today} tasks · {agent.tasks_completed} done
        </p>
      </div>
      <span
        className={clsx(
          "px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded-full border",
          agent.status === "running" && "text-[var(--color-success)] border-[var(--color-success)]/20 bg-[var(--color-success)]/5",
          agent.status === "idle" && "text-[var(--color-text-muted)] border-[var(--color-border)]",
          agent.status === "error" && "text-[var(--color-danger)] border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5"
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

  useEventSource<ActivityEvent>("/api/activity/stream", {
    onEvent: (event) => {
      if (event.event_type === "connected" || !event.title) return;
      setRecentEvents((prev) => [event, ...prev].slice(0, 10));
    },
  });

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

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const activeAgents = activityStats?.agents.filter((a) => a.status === "running").length ?? 0;
  const totalAgents = activityStats?.agents.length ?? 0;
  const tasksCompleted = reviewStats?.approved_today ?? 0;
  const pendingReview = reviewStats?.pending_review ?? 0;
  const memoryCount = memoryStats?.total_memories ?? 0;
  const knowledgeCount = knowledgeStats?.total_items ?? 0;

  return (
    <div className="space-y-8 max-w-6xl">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
          Overview of your AI operating system
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Agents"
          value={`${activeAgents}/${totalAgents}`}
          sub={`${activityStats?.total_events_today ?? 0} events today`}
          loading={loading}
        />
        <StatCard
          label="Completed"
          value={String(tasksCompleted)}
          sub={`${pendingReview} pending review`}
          loading={loading}
        />
        <StatCard
          label="Approvals"
          value={String(activityStats?.pending_approvals ?? 0)}
          sub={`${reviewStats?.rejected_today ?? 0} rejected`}
          loading={loading}
        />
        <StatCard
          label="Memory"
          value={String(memoryCount)}
          sub={`${knowledgeCount} knowledge items`}
          loading={loading}
        />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Actions */}
          <div>
            <h2 className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2.5">
              Quick Actions
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <QuickAction
                title="Chat with Agents"
                description="Auto-delegates to specialists"
                href="/dashboard/chat"
                icon={Bot}
              />
              <QuickAction
                title="Review Tasks"
                description={pendingReview > 0 ? `${pendingReview} need review` : "Approve outputs"}
                href="/dashboard/tasks"
                icon={ListTodo}
              />
              <QuickAction
                title="Weekly Planner"
                description="AI schedule optimization"
                href="/dashboard/planner"
                icon={CalendarDays}
              />
              <QuickAction
                title="Knowledge Base"
                description={knowledgeCount > 0 ? `${knowledgeCount} items indexed` : "Upload docs"}
                href="/dashboard/knowledge"
                icon={Brain}
              />
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium">Recent Activity</h2>
              <Link
                href="/dashboard/agents"
                className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
              >
                View all
              </Link>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-4 h-4 animate-spin text-[var(--color-text-muted)]" />
                </div>
              ) : recentEvents.length === 0 ? (
                <div className="py-8 text-center">
                  <Activity className="w-6 h-6 text-[var(--color-text-muted)] mx-auto mb-2" />
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    No activity yet. Start from Chat.
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

        {/* Right column */}
        <div className="space-y-6">
          {/* Active Agents */}
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium">Agents</h2>
              <Link
                href="/dashboard/agents"
                className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
              >
                View all
              </Link>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-4 h-4 animate-spin text-[var(--color-text-muted)]" />
                </div>
              ) : activityStats?.agents && activityStats.agents.length > 0 ? (
                activityStats.agents.slice(0, 5).map((agent) => (
                  <AgentRow key={agent.agent_name} agent={agent} />
                ))
              ) : (
                <div className="py-8 text-center">
                  <Bot className="w-6 h-6 text-[var(--color-text-muted)] mx-auto mb-2" />
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    No agents registered.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Review Queue */}
          <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium">Review Queue</h2>
              <Link
                href="/dashboard/tasks"
                className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
              >
                View all
              </Link>
            </div>
            <div className="space-y-2">
              {[
                { label: "Pending", value: reviewStats?.pending_review ?? 0, icon: Eye },
                { label: "Approved", value: reviewStats?.approved_today ?? 0, icon: CheckCircle2 },
                { label: "Rejected", value: reviewStats?.rejected_today ?? 0, icon: XCircle },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2.5 p-2.5 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <item.icon className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
                  <span className="text-sm flex-1">{item.label}</span>
                  <span className="text-sm font-medium tabular-nums">{loading ? "—" : item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
