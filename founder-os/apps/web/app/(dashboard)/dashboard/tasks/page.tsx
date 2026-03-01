"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import {
  ListTodo,
  CheckCircle2,
  XCircle,
  Pencil,
  Star,
  Bot,
  ChevronDown,
  Filter,
  Loader2,
  RefreshCw,
  Clock,
  ArrowLeft,
  RotateCcw,
  MessageSquare,
  FileText,
  AlertTriangle,
  ChevronRight,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  Eye,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ───────────────────────────────────────────── */
interface TaskListItem {
  id: string;
  title: string;
  description: string | null;
  task_type: string | null;
  status: string;
  priority: number;
  agent_name: string;
  agent_display_name: string;
  requires_approval: boolean;
  output_preview: string | null;
  created_at: string;
  completed_at: string | null;
}

interface TaskOutput {
  id: string;
  output_type: string | null;
  title: string | null;
  content: string | null;
  format: string | null;
  word_count: number | null;
  version: number;
  publish_status: string;
  user_rating: number | null;
  user_feedback: string | null;
  created_at: string;
}

interface TaskDetail {
  id: string;
  title: string;
  description: string | null;
  task_type: string | null;
  status: string;
  priority: number;
  agent_name: string;
  agent_display_name: string;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  outputs: TaskOutput[];
  requires_approval: boolean;
  approved_at: string | null;
  approval_notes: string | null;
  tokens_used: number | null;
  cost_usd: number | null;
  duration_seconds: number | null;
  attempts: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

interface ReviewStats {
  pending_review: number;
  approved_today: number;
  rejected_today: number;
  edited_today: number;
  total_tasks: number;
  avg_rating: number | null;
}

/* ── Agent colors ────────────────────────────────────── */
const agentColors: Record<string, string> = {
  orchestrator: "from-violet-500 to-purple-600",
  planner: "from-blue-500 to-indigo-600",
  content: "from-pink-500 to-rose-600",
  research: "from-emerald-500 to-teal-600",
  ops: "from-amber-500 to-orange-600",
  product: "from-cyan-500 to-blue-600",
  support: "from-lime-500 to-green-600",
  unknown: "from-gray-500 to-slate-600",
};

/* ── Status styling ──────────────────────────────────── */
const statusConfig: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  pending: { label: "Pending", color: "text-gray-500 bg-gray-500/10", icon: Clock },
  pending_review: { label: "Needs Review", color: "text-amber-600 bg-amber-500/10", icon: Eye },
  completed: { label: "Completed", color: "text-blue-500 bg-blue-500/10", icon: CheckCircle2 },
  approved: { label: "Approved", color: "text-emerald-500 bg-emerald-500/10", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "text-red-500 bg-red-500/10", icon: XCircle },
  failed: { label: "Failed", color: "text-red-500 bg-red-500/10", icon: AlertTriangle },
  running: { label: "Running", color: "text-indigo-500 bg-indigo-500/10", icon: Loader2 },
};

const priorityLabels: Record<number, { label: string; color: string }> = {
  1: { label: "Low", color: "text-gray-500" },
  2: { label: "Medium", color: "text-amber-500" },
  3: { label: "High", color: "text-orange-500" },
  4: { label: "Critical", color: "text-red-500" },
};

/* ── Time formatting ─────────────────────────────────── */
function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/* ── StatusBadge component ───────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] ?? statusConfig.pending!;
  const Icon = cfg!.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium", cfg.color)}>
      <Icon className={clsx("w-3 h-3", status === "running" && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

/* ── Star rating component ───────────────────────────── */
function StarRating({
  value,
  onChange,
  readonly = false,
}: {
  value: number;
  onChange?: (v: number) => void;
  readonly?: boolean;
}) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <button
          key={s}
          disabled={readonly}
          onClick={() => onChange?.(s)}
          className={clsx(
            "transition-colors",
            readonly ? "cursor-default" : "cursor-pointer hover:text-amber-400"
          )}
        >
          <Star
            className={clsx(
              "w-4 h-4",
              s <= value ? "text-amber-400 fill-amber-400" : "text-gray-300 dark:text-gray-600"
            )}
          />
        </button>
      ))}
    </div>
  );
}

/* ── Task List Row ───────────────────────────────────── */
function TaskRow({
  task,
  selected,
  onClick,
}: {
  task: TaskListItem;
  selected: boolean;
  onClick: () => void;
}) {
  const gradient = agentColors[task.agent_name] || agentColors.unknown;
  const pri = priorityLabels[task.priority] ?? { label: "Low", color: "text-gray-500" };

  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full text-left px-4 py-3 flex items-start gap-3 transition-colors border-l-[3px]",
        selected
          ? "bg-indigo-50/50 dark:bg-indigo-500/5 border-l-indigo-500"
          : "hover:bg-[var(--color-surface-muted)] border-l-transparent"
      )}
    >
      <div
        className={clsx(
          "w-8 h-8 rounded-lg bg-gradient-to-br flex items-center justify-center shrink-0 mt-0.5",
          gradient
        )}
      >
        <Bot className="w-4 h-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-sm font-medium truncate">{task.title}</p>
          {task.requires_approval && task.status !== "approved" && (
            <span className="shrink-0 w-2 h-2 rounded-full bg-amber-400" title="Needs approval" />
          )}
        </div>
        <div className="flex items-center gap-2 mb-1">
          <StatusBadge status={task.status} />
          <span className={clsx("text-[10px] font-medium", pri.color)}>{pri.label}</span>
        </div>
        {task.output_preview && (
          <p className="text-xs text-[var(--color-text-secondary)] line-clamp-1">
            {task.output_preview}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {task.agent_display_name}
          </span>
          <span className="text-[10px] text-[var(--color-text-muted)]">·</span>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {formatDate(task.created_at)}
          </span>
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-[var(--color-text-muted)] shrink-0 mt-2" />
    </button>
  );
}

/* ── Task Detail Panel ───────────────────────────────── */
function TaskDetailPanel({
  taskId,
  api,
  onBack,
  onAction,
}: {
  taskId: string;
  api: ReturnType<typeof useApi>;
  onBack: () => void;
  onAction: () => void;
}) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Edit mode
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [editNotes, setEditNotes] = useState("");

  // Reject mode
  const [rejectMode, setRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [retryOnReject, setRetryOnReject] = useState(false);

  // Feedback mode
  const [feedbackMode, setFeedbackMode] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComments, setFeedbackComments] = useState("");

  useEffect(() => {
    setLoading(true);
    setEditMode(false);
    setRejectMode(false);
    setFeedbackMode(false);
    api(`/api/review/tasks/${taskId}`)
      .then((data) => {
        setTask(data);
        if (data.outputs?.length) {
          const latest = [...data.outputs].sort(
            (a: TaskOutput, b: TaskOutput) => b.version - a.version
          )[0];
          setEditContent(latest.content || "");
        }
      })
      .catch(() => setTask(null))
      .finally(() => setLoading(false));
  }, [taskId, api]);

  async function handleApprove() {
    setActionLoading("approve");
    try {
      await api(`/api/review/tasks/${taskId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: "Approved from dashboard" }),
      });
      onAction();
    } finally {
      setActionLoading(null);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) return;
    setActionLoading("reject");
    try {
      await api(`/api/review/tasks/${taskId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason, retry: retryOnReject }),
      });
      onAction();
    } finally {
      setActionLoading(null);
      setRejectMode(false);
    }
  }

  async function handleEdit() {
    if (!editContent.trim()) return;
    setActionLoading("edit");
    try {
      await api(`/api/review/tasks/${taskId}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          edited_content: editContent,
          edit_notes: editNotes || undefined,
        }),
      });
      onAction();
    } finally {
      setActionLoading(null);
      setEditMode(false);
    }
  }

  async function handleFeedback() {
    if (feedbackRating === 0) return;
    setActionLoading("feedback");
    try {
      await api(`/api/review/tasks/${taskId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating: feedbackRating,
          comments: feedbackComments || undefined,
        }),
      });
      setFeedbackMode(false);
      // Reload task to show updated rating
      const data = await api(`/api/review/tasks/${taskId}`);
      setTask(data);
    } finally {
      setActionLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <AlertTriangle className="w-10 h-10 text-red-400 mb-3" />
        <p className="font-semibold">Task not found</p>
        <button onClick={onBack} className="mt-3 text-sm text-indigo-500 hover:underline">
          Back to list
        </button>
      </div>
    );
  }

  const gradient = agentColors[task.agent_name] || agentColors.unknown;
  const latestOutput = task.outputs?.length
    ? [...task.outputs].sort((a, b) => b.version - a.version)[0]
    : null;

  const canReview = ["completed", "pending_review", "pending"].includes(task.status);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-3 border-b border-[var(--color-border)] flex items-center gap-3">
        <button
          onClick={onBack}
          className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors lg:hidden"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div
          className={clsx(
            "w-8 h-8 rounded-lg bg-gradient-to-br flex items-center justify-center",
            gradient
          )}
        >
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{task.title}</p>
          <p className="text-xs text-[var(--color-text-secondary)]">
            {task.agent_display_name} · {formatDate(task.created_at)}
          </p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Description */}
        {task.description && (
          <div>
            <p className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-1">
              Description
            </p>
            <p className="text-sm text-[var(--color-text-primary)]">{task.description}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Priority", value: (priorityLabels[task.priority] ?? { label: "Low", color: "text-gray-500" }).label },
            { label: "Attempts", value: String(task.attempts) },
            { label: "Tokens", value: task.tokens_used ? task.tokens_used.toLocaleString() : "—" },
            {
              label: "Cost",
              value: task.cost_usd != null ? `$${task.cost_usd.toFixed(4)}` : "—",
            },
          ].map((m) => (
            <div
              key={m.label}
              className="bg-[var(--color-surface-muted)] rounded-xl px-3 py-2"
            >
              <p className="text-[10px] text-[var(--color-text-muted)] mb-0.5">{m.label}</p>
              <p className="text-sm font-semibold">{m.value}</p>
            </div>
          ))}
        </div>

        {/* Error */}
        {task.error_message && (
          <div className="bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20 rounded-xl px-4 py-3">
            <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-1 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" /> Error
            </p>
            <p className="text-xs text-red-700 dark:text-red-300 font-mono">{task.error_message}</p>
          </div>
        )}

        {/* Output */}
        {latestOutput && !editMode && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                Output{" "}
                <span className="text-[10px] font-normal text-[var(--color-text-muted)]">
                  v{latestOutput.version}
                </span>
              </p>
              {latestOutput.word_count && (
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  {latestOutput.word_count} words
                </span>
              )}
            </div>
            <div className="bg-[var(--color-surface-muted)] rounded-xl p-4 text-sm whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
              {latestOutput.content || "No content"}
            </div>
            {latestOutput.user_rating && (
              <div className="mt-2 flex items-center gap-2">
                <StarRating value={latestOutput.user_rating} readonly />
                {latestOutput.user_feedback && (
                  <span className="text-xs text-[var(--color-text-secondary)] italic">
                    "{latestOutput.user_feedback}"
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Edit mode */}
        {editMode && (
          <div>
            <p className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Pencil className="w-3.5 h-3.5" />
              Edit Output
            </p>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-64 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <input
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              placeholder="Notes about your edits (optional)"
              className="mt-2 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleEdit}
                disabled={actionLoading === "edit"}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
              >
                {actionLoading === "edit" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
                Save & Approve
              </button>
              <button
                onClick={() => setEditMode(false)}
                className="px-4 py-2 text-sm font-medium rounded-xl hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Reject mode */}
        {rejectMode && (
          <div className="bg-red-50/50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20 rounded-xl p-4">
            <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-2 flex items-center gap-1.5">
              <XCircle className="w-3.5 h-3.5" />
              Reject Task
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection..."
              className="w-full h-24 rounded-lg border border-red-200 dark:border-red-500/30 bg-[var(--color-surface)] p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-500/50"
            />
            <div className="flex items-center gap-3 mt-2">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={retryOnReject}
                  onChange={(e) => setRetryOnReject(e.target.checked)}
                  className="w-4 h-4 rounded border-[var(--color-border)] text-indigo-500"
                />
                <RotateCcw className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
                Retry with agent
              </label>
            </div>
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim() || actionLoading === "reject"}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-red-500 rounded-xl hover:bg-red-600 transition-colors disabled:opacity-50"
              >
                {actionLoading === "reject" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <XCircle className="w-4 h-4" />
                )}
                Reject
              </button>
              <button
                onClick={() => setRejectMode(false)}
                className="px-4 py-2 text-sm font-medium rounded-xl hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Feedback mode */}
        {feedbackMode && (
          <div className="bg-indigo-50/50 dark:bg-indigo-500/5 border border-indigo-200 dark:border-indigo-500/20 rounded-xl p-4">
            <p className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 mb-2 flex items-center gap-1.5">
              <MessageSquare className="w-3.5 h-3.5" />
              Leave Feedback
            </p>
            <div className="mb-3">
              <p className="text-xs text-[var(--color-text-secondary)] mb-1">Rating</p>
              <StarRating value={feedbackRating} onChange={setFeedbackRating} />
            </div>
            <textarea
              value={feedbackComments}
              onChange={(e) => setFeedbackComments(e.target.value)}
              placeholder="Comments (optional)..."
              className="w-full h-20 rounded-lg border border-indigo-200 dark:border-indigo-500/30 bg-[var(--color-surface)] p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleFeedback}
                disabled={feedbackRating === 0 || actionLoading === "feedback"}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl hover:shadow-lg transition-all disabled:opacity-50"
              >
                {actionLoading === "feedback" ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Star className="w-4 h-4" />
                )}
                Submit
              </button>
              <button
                onClick={() => setFeedbackMode(false)}
                className="px-4 py-2 text-sm font-medium rounded-xl hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Approval notes */}
        {task.approval_notes && (
          <div className="bg-[var(--color-surface-muted)] rounded-xl px-4 py-3">
            <p className="text-xs font-semibold text-[var(--color-text-secondary)] mb-1">
              Review Notes
            </p>
            <p className="text-sm">{task.approval_notes}</p>
          </div>
        )}

        {/* Output version history */}
        {task.outputs.length > 1 && (
          <div>
            <p className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-2">
              Version History
            </p>
            <div className="space-y-1">
              {[...task.outputs]
                .sort((a, b) => b.version - a.version)
                .map((o) => (
                  <div
                    key={o.id}
                    className="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--color-surface-muted)] text-xs"
                  >
                    <span className="font-medium">v{o.version}</span>
                    <span className="text-[var(--color-text-muted)]">
                      {o.word_count} words · {formatDate(o.created_at)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Action bar */}
      {canReview && !editMode && !rejectMode && !feedbackMode && (
        <div className="px-5 py-3 border-t border-[var(--color-border)] flex items-center gap-2 bg-[var(--color-surface)]">
          <button
            onClick={handleApprove}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-emerald-500 rounded-xl hover:bg-emerald-600 transition-colors disabled:opacity-50"
          >
            {actionLoading === "approve" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ThumbsUp className="w-4 h-4" />
            )}
            Approve
          </button>
          <button
            onClick={() => {
              setRejectMode(true);
              setEditMode(false);
              setFeedbackMode(false);
            }}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-xl border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/5 transition-colors disabled:opacity-50"
          >
            <ThumbsDown className="w-4 h-4" />
            Reject
          </button>
          {latestOutput && (
            <button
              onClick={() => {
                setEditMode(true);
                setRejectMode(false);
                setFeedbackMode(false);
              }}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-xl border border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] transition-colors disabled:opacity-50"
            >
              <Pencil className="w-4 h-4" />
              Edit
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={() => {
              setFeedbackMode(true);
              setEditMode(false);
              setRejectMode(false);
            }}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-xl hover:bg-[var(--color-surface-muted)] transition-colors text-[var(--color-text-secondary)] disabled:opacity-50"
          >
            <MessageSquare className="w-4 h-4" />
            Feedback
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Main Page ───────────────────────────────────────── */
export default function TasksPage() {
  const api = useApi();
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [needsReview, setNeedsReview] = useState(false);

  /* ── Fetch tasks ── */
  const fetchTasks = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (needsReview) params.set("needs_review", "true");
      params.set("limit", "50");

      const [tasksData, statsData] = await Promise.all([
        api(`/api/review/tasks?${params.toString()}`).catch(() => ({ tasks: [], total: 0 })),
        api("/api/review/stats").catch(() => null),
      ]);

      setTasks(tasksData.tasks || []);
      setTotal(tasksData.total || 0);
      if (statsData) setStats(statsData);
    } catch {
      // API not ready
    } finally {
      setLoading(false);
    }
  }, [api, statusFilter, needsReview]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  /* ── Polling (every 10s) ── */
  useEffect(() => {
    const interval = setInterval(fetchTasks, 10000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  function handleAction() {
    setSelectedId(null);
    fetchTasks();
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Task Review</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Review, approve, and edit agent outputs
          </p>
        </div>
        <button
          onClick={fetchTasks}
          className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-[var(--color-text-secondary)]" />
        </button>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: "Pending", value: stats.pending_review, icon: Eye, iconColor: "text-amber-500 bg-amber-500/10" },
            { label: "Approved", value: stats.approved_today, icon: ThumbsUp, iconColor: "text-emerald-500 bg-emerald-500/10" },
            { label: "Rejected", value: stats.rejected_today, icon: ThumbsDown, iconColor: "text-red-500 bg-red-500/10" },
            { label: "Edited", value: stats.edited_today, icon: Pencil, iconColor: "text-blue-500 bg-blue-500/10" },
            { label: "Total", value: stats.total_tasks, icon: ListTodo, iconColor: "text-indigo-500 bg-indigo-500/10" },
            {
              label: "Avg Rating",
              value: stats.avg_rating ? stats.avg_rating.toFixed(1) : "—",
              icon: Star,
              iconColor: "text-amber-500 bg-amber-500/10",
            },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-3 flex items-center gap-2.5"
            >
              <div className={clsx("p-2 rounded-xl", s.iconColor)}>
                <s.icon className="w-4 h-4" />
              </div>
              <div>
                <p className="text-lg font-bold leading-tight">{s.value}</p>
                <p className="text-[10px] text-[var(--color-text-muted)]">{s.label}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Main content — list + detail split */}
      <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] overflow-hidden min-h-[600px] flex">
        {/* Task list panel */}
        <div
          className={clsx(
            "w-full lg:w-[380px] lg:border-r border-[var(--color-border)] flex flex-col shrink-0",
            selectedId && "hidden lg:flex"
          )}
        >
          {/* Filters */}
          <div className="px-4 py-3 border-b border-[var(--color-border)] flex items-center gap-2">
            <div className="relative flex-1">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="appearance-none w-full text-xs pl-7 pr-6 py-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-primary)] cursor-pointer"
              >
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="pending_review">Needs Review</option>
                <option value="completed">Completed</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="failed">Failed</option>
              </select>
              <Filter className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-text-muted)]" />
              <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-text-muted)]" />
            </div>
            <button
              onClick={() => setNeedsReview(!needsReview)}
              className={clsx(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                needsReview
                  ? "border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400"
                  : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)]"
              )}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Needs Review
            </button>
          </div>

          {/* Task list */}
          <div className="flex-1 overflow-y-auto divide-y divide-[var(--color-border)]">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              </div>
            ) : tasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center px-6">
                <ListTodo className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
                <h3 className="text-lg font-semibold mb-1">No tasks found</h3>
                <p className="text-sm text-[var(--color-text-secondary)] max-w-xs">
                  {needsReview
                    ? "No tasks are currently waiting for your review."
                    : "Tasks will appear here as agents complete their work."}
                </p>
              </div>
            ) : (
              tasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  selected={task.id === selectedId}
                  onClick={() => setSelectedId(task.id)}
                />
              ))
            )}
          </div>

          {/* Footer */}
          {tasks.length > 0 && (
            <div className="px-4 py-2 border-t border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
              Showing {tasks.length} of {total} tasks
            </div>
          )}
        </div>

        {/* Detail panel */}
        <div
          className={clsx(
            "flex-1 min-w-0",
            !selectedId && "hidden lg:flex"
          )}
        >
          {selectedId ? (
            <TaskDetailPanel
              taskId={selectedId}
              api={api}
              onBack={() => setSelectedId(null)}
              onAction={handleAction}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <FileText className="w-16 h-16 text-[var(--color-text-muted)] mb-4" />
              <h3 className="text-lg font-semibold mb-1">Select a task</h3>
              <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">
                Choose a task from the list to review its output, approve, edit,
                or reject it.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
