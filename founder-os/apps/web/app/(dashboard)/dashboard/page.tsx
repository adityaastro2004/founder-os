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
  XCircle,
  Wrench,
  GitBranch,
  Play,
  Eye,
} from "lucide-react";
import Link from "next/link";
import {
  PageHeader,
  StatCard,
  Card,
  Badge,
  Skeleton,
} from "@/app/_components/ui";

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

/* ── Activity item ────────────────────────────────── */
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
      <div className="shrink-0 rounded-md bg-surface-muted p-1.5">
        <Icon className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{event.title}</p>
        {event.description && (
          <p className="mt-0.5 line-clamp-1 text-xs text-ink-secondary">
            {event.description}
          </p>
        )}
      </div>
      <span className="whitespace-nowrap text-[11px] text-ink-secondary">
        {timeAgo(event.timestamp)}
      </span>
    </div>
  );
}

/* ── Quick action card ────────────────────────────── */
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
      className="group flex items-center gap-3 rounded-card border border-line bg-surface p-3.5 transition-colors duration-150 hover:bg-surface-muted/50"
    >
      <div className="rounded-md bg-surface-muted p-2 transition-colors duration-150 group-hover:bg-surface">
        <Icon className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-xs text-ink-secondary">{description}</p>
      </div>
      <ArrowRight
        className="h-3.5 w-3.5 text-ink-muted transition-transform duration-150 group-hover:translate-x-0.5"
        aria-hidden="true"
      />
    </Link>
  );
}

/* ── Agent row ─────────────────────────────────────── */
function AgentRow({ agent }: { agent: AgentStatus }) {
  const tone =
    agent.status === "running"
      ? "success"
      : agent.status === "error"
        ? "danger"
        : "neutral";
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-muted">
        <Bot className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{agent.display_name}</p>
        <p className="text-[11px] text-ink-secondary">
          {agent.tasks_today} tasks · {agent.tasks_completed} done
        </p>
      </div>
      <Badge tone={tone}>{agent.status}</Badge>
    </div>
  );
}

/* ── Section list wrapper ─────────────────────────── */
function ListCard({
  title,
  viewAllHref,
  children,
}: {
  title: string;
  viewAllHref: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium text-ink">{title}</h2>
        <Link
          href={viewAllHref}
          className="text-xs text-ink-secondary transition-colors duration-150 hover:text-ink"
        >
          View all
        </Link>
      </div>
      {children}
    </Card>
  );
}

function ListLoading() {
  return (
    <div className="space-y-3 py-2">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-4/5" />
    </div>
  );
}

/* ── Dashboard page ───────────────────────────────── */
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
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        description="Overview of your AI operating system"
      />

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
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
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column */}
        <div className="space-y-6 lg:col-span-2">
          {/* Quick actions */}
          <div>
            <h2 className="mb-2.5 text-[13px] font-medium text-ink-secondary">
              Quick actions
            </h2>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <QuickAction
                title="Chat with agents"
                description="Auto-delegates to specialists"
                href="/dashboard/chat"
                icon={Bot}
              />
              <QuickAction
                title="Review tasks"
                description={pendingReview > 0 ? `${pendingReview} need review` : "Approve outputs"}
                href="/dashboard/tasks"
                icon={ListTodo}
              />
              <QuickAction
                title="Weekly planner"
                description="AI schedule optimization"
                href="/dashboard/planner"
                icon={CalendarDays}
              />
              <QuickAction
                title="Knowledge base"
                description={knowledgeCount > 0 ? `${knowledgeCount} items indexed` : "Upload docs"}
                href="/dashboard/knowledge"
                icon={Brain}
              />
            </div>
          </div>

          {/* Recent activity */}
          <ListCard title="Recent activity" viewAllHref="/dashboard/agents">
            <div className="divide-y divide-line-subtle">
              {loading ? (
                <ListLoading />
              ) : recentEvents.length === 0 ? (
                <div className="py-8 text-center">
                  <Activity
                    className="mx-auto mb-2 h-6 w-6 text-ink-muted"
                    aria-hidden="true"
                  />
                  <p className="text-sm text-ink-secondary">
                    Nothing yet today. Agent activity will stream in here as it
                    happens.
                  </p>
                </div>
              ) : (
                recentEvents.slice(0, 5).map((event) => (
                  <ActivityItem key={event.id} event={event} />
                ))
              )}
            </div>
          </ListCard>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Active agents */}
          <ListCard title="Agents" viewAllHref="/dashboard/agents">
            <div className="divide-y divide-line-subtle">
              {loading ? (
                <ListLoading />
              ) : activityStats?.agents && activityStats.agents.length > 0 ? (
                activityStats.agents.slice(0, 5).map((agent) => (
                  <AgentRow key={agent.agent_name} agent={agent} />
                ))
              ) : (
                <div className="py-8 text-center">
                  <Bot
                    className="mx-auto mb-2 h-6 w-6 text-ink-muted"
                    aria-hidden="true"
                  />
                  <p className="text-sm text-ink-secondary">
                    No agents registered yet.
                  </p>
                </div>
              )}
            </div>
          </ListCard>

          {/* Review queue */}
          <ListCard title="Review queue" viewAllHref="/dashboard/tasks">
            <div className="space-y-2">
              {[
                { label: "Pending", value: reviewStats?.pending_review ?? 0, icon: Eye },
                { label: "Approved", value: reviewStats?.approved_today ?? 0, icon: CheckCircle2 },
                { label: "Rejected", value: reviewStats?.rejected_today ?? 0, icon: XCircle },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2.5 rounded-control border border-line bg-surface-muted/40 p-2.5"
                >
                  <item.icon className="h-3.5 w-3.5 text-ink-muted" aria-hidden="true" />
                  <span className="flex-1 text-sm text-ink">{item.label}</span>
                  <span className="text-sm font-medium tabular-nums text-ink">
                    {loading ? "—" : item.value}
                  </span>
                </div>
              ))}
            </div>
          </ListCard>
        </div>
      </div>
    </div>
  );
}
