import {
  Bot,
  CalendarDays,
  Brain,
  ListTodo,
  Zap,
  TrendingUp,
  Clock,
  CheckCircle2,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

/* ── Stat Card ─────────────────────────────────────── */
function StatCard({
  label,
  value,
  change,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  change: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--color-text-secondary)]">{label}</p>
          <p className="text-2xl font-bold mt-1 tracking-tight">{value}</p>
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" />
            {change}
          </p>
        </div>
        <div
          className={`p-2.5 rounded-xl ${color}`}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}

/* ── Activity Item ────────────────────────────────── */
function ActivityItem({
  title,
  description,
  time,
  icon: Icon,
  color,
}: {
  title: string;
  description: string;
  time: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="flex items-start gap-3 py-3">
      <div className={`p-2 rounded-lg shrink-0 ${color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{title}</p>
        <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 line-clamp-1">
          {description}
        </p>
      </div>
      <span className="text-xs text-[var(--color-text-muted)] whitespace-nowrap">
        {time}
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
function AgentRow({
  name,
  status,
  task,
}: {
  name: string;
  status: "running" | "idle" | "completed";
  task: string;
}) {
  const statusStyles = {
    running:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    idle: "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    completed:
      "bg-slate-100 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400",
  };

  return (
    <div className="flex items-center gap-3 py-3">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{name}</p>
        <p className="text-xs text-[var(--color-text-secondary)] truncate">
          {task}
        </p>
      </div>
      <span
        className={`px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full ${statusStyles[status]}`}
      >
        {status}
      </span>
    </div>
  );
}

/* ── Dashboard Page ───────────────────────────────── */
export default function DashboardPage() {
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
          value="3"
          change="+1 this week"
          icon={Bot}
          color="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
        />
        <StatCard
          label="Tasks Completed"
          value="24"
          change="+8 today"
          icon={CheckCircle2}
          color="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
        />
        <StatCard
          label="Upcoming Events"
          value="5"
          change="Next in 2h"
          icon={CalendarDays}
          color="bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
        />
        <StatCard
          label="Memory Entries"
          value="142"
          change="+12 this week"
          icon={Brain}
          color="bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400"
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
                title="Launch Agent"
                description="Deploy a new AI agent"
                href="/dashboard/agents"
                icon={Bot}
                color="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
              />
              <QuickAction
                title="Create Task"
                description="Add a new task to your queue"
                href="/dashboard/tasks"
                icon={ListTodo}
                color="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
              />
              <QuickAction
                title="Schedule Meeting"
                description="Plan your next event"
                href="/dashboard/planner"
                icon={CalendarDays}
                color="bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
              />
              <QuickAction
                title="New Automation"
                description="Set up a workflow"
                href="/dashboard/automations"
                icon={Zap}
                color="bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400"
              />
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
            <h2 className="text-lg font-semibold mb-1">Recent Activity</h2>
            <p className="text-xs text-[var(--color-text-secondary)] mb-4">
              Latest actions from you and your agents
            </p>
            <div className="divide-y divide-[var(--color-border)]">
              <ActivityItem
                title="Research Agent completed task"
                description='Finished analyzing "Q4 Market Trends" — 12 sources processed'
                time="5m ago"
                icon={CheckCircle2}
                color="bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
              />
              <ActivityItem
                title="New memory stored"
                description='Saved preference: "Prefers concise executive summaries"'
                time="23m ago"
                icon={Brain}
                color="bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400"
              />
              <ActivityItem
                title="Email Agent sending outreach"
                description="Drafted and queued 3 follow-up emails for approval"
                time="1h ago"
                icon={Bot}
                color="bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
              />
              <ActivityItem
                title="Calendar synced"
                description="Imported 5 events from Google Calendar"
                time="2h ago"
                icon={CalendarDays}
                color="bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400"
              />
              <ActivityItem
                title="Automation triggered"
                description='"Weekly Report" automation ran successfully'
                time="4h ago"
                icon={Zap}
                color="bg-sky-100 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400"
              />
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
              <AgentRow
                name="Research Agent"
                status="running"
                task="Analyzing competitor landscape"
              />
              <AgentRow
                name="Email Agent"
                status="idle"
                task="Waiting for approval on drafts"
              />
              <AgentRow
                name="Scheduler Agent"
                status="running"
                task="Optimizing next week's calendar"
              />
            </div>
          </div>

          {/* Upcoming Today */}
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Today&apos;s Schedule</h2>
              <Link
                href="/dashboard/planner"
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                View calendar
              </Link>
            </div>
            <div className="space-y-3">
              {[
                { time: "09:00", title: "Team standup", duration: "15 min" },
                {
                  time: "11:00",
                  title: "Product review",
                  duration: "45 min",
                },
                {
                  time: "14:30",
                  title: "Investor call",
                  duration: "30 min",
                },
              ].map((event) => (
                <div
                  key={event.time}
                  className="flex items-center gap-3 p-3 rounded-xl bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <div className="flex flex-col items-center w-12 shrink-0">
                    <Clock className="w-3.5 h-3.5 text-[var(--color-text-muted)] mb-0.5" />
                    <span className="text-xs font-semibold">{event.time}</span>
                  </div>
                  <div className="h-8 w-px bg-indigo-300 dark:bg-indigo-500/30 rounded-full" />
                  <div>
                    <p className="text-sm font-medium">{event.title}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {event.duration}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
