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
import { PageHeader, Card, Button } from "@/app/_components/ui";

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
  orchestrator: "bg-ink",
  planner: "bg-ink-secondary",
  content: "bg-accent",
  research: "bg-success",
  support: "bg-warning",
  unknown: "bg-ink-muted",
};

/* ── Status styling ──────────────────────────────────── */
const statusConfig: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  pending: { label: "Pending", color: "text-ink-secondary bg-surface-muted", icon: Clock },
  pending_review: { label: "Needs review", color: "text-warning bg-warning-soft", icon: Eye },
  completed: { label: "Completed", color: "text-ink-secondary bg-surface-muted", icon: CheckCircle2 },
  approved: { label: "Approved", color: "text-success bg-success-soft", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "text-danger bg-danger-soft", icon: XCircle },
  failed: { label: "Failed", color: "text-danger bg-danger-soft", icon: AlertTriangle },
  running: { label: "Running", color: "text-ink-secondary bg-surface-muted", icon: Loader2 },
};

const priorityLabels: Record<number, { label: string; color: string }> = {
  1: { label: "Low", color: "text-ink-secondary" },
  2: { label: "Medium", color: "text-ink-secondary" },
  3: { label: "High", color: "text-warning" },
  4: { label: "Critical", color: "text-danger" },
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

/* ── Status badge ────────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const cfg = statusConfig[status] ?? statusConfig.pending!;
  const Icon = cfg!.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium", cfg.color)}>
      <Icon className={clsx("h-3 w-3", status === "running" && "animate-spin")} aria-hidden="true" />
      {cfg.label}
    </span>
  );
}

/* ── Star rating ─────────────────────────────────────── */
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
          type="button"
          disabled={readonly}
          onClick={() => onChange?.(s)}
          aria-label={`Rate ${s} of 5`}
          className={clsx(
            "transition-colors duration-150",
            readonly ? "cursor-default" : "cursor-pointer hover:text-ink-secondary"
          )}
        >
          <Star
            className={clsx(
              "h-4 w-4",
              s <= value ? "fill-warning text-warning" : "text-line"
            )}
            aria-hidden="true"
          />
        </button>
      ))}
    </div>
  );
}

/* ── Task list row ───────────────────────────────────── */
function TaskRow({
  task,
  selected,
  onClick,
}: {
  task: TaskListItem;
  selected: boolean;
  onClick: () => void;
}) {
  const accentBg = agentColors[task.agent_name] || agentColors.unknown;
  const pri = priorityLabels[task.priority] ?? { label: "Low", color: "text-ink-secondary" };

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex w-full items-start gap-3 border-l-[3px] px-4 py-3 text-left transition-colors duration-150",
        selected
          ? "border-l-accent bg-surface-muted"
          : "border-l-transparent hover:bg-surface-muted/60"
      )}
    >
      <div
        className={clsx(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
          accentBg
        )}
      >
        <Bot className="h-4 w-4 text-white" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-2">
          <p className="truncate text-sm font-medium text-ink">{task.title}</p>
          {task.requires_approval && task.status !== "approved" && (
            <span className="h-2 w-2 shrink-0 rounded-full bg-warning" title="Needs approval" />
          )}
        </div>
        <div className="mb-1 flex items-center gap-2">
          <StatusBadge status={task.status} />
          <span className={clsx("text-[10px] font-medium", pri.color)}>{pri.label}</span>
        </div>
        {task.output_preview && (
          <p className="line-clamp-1 text-xs text-ink-secondary">
            {task.output_preview}
          </p>
        )}
        <div className="mt-1 flex items-center gap-2 text-[10px] text-ink-secondary">
          <span>{task.agent_display_name}</span>
          <span>·</span>
          <span>{formatDate(task.created_at)}</span>
        </div>
      </div>
      <ChevronRight className="mt-2 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
    </button>
  );
}

/* ── Task detail panel ───────────────────────────────── */
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

  const [actionError, setActionError] = useState<string | null>(null);

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
    setActionError(null);
    try {
      await api(`/api/review/tasks/${taskId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: "Approved from dashboard" }),
      });
      onAction();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve task");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) return;
    setActionLoading("reject");
    setActionError(null);
    try {
      await api(`/api/review/tasks/${taskId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason, retry: retryOnReject }),
      });
      onAction();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject task");
    } finally {
      setActionLoading(null);
      setRejectMode(false);
    }
  }

  async function handleEdit() {
    if (!editContent.trim()) return;
    setActionLoading("edit");
    setActionError(null);
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
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to save edits");
    } finally {
      setActionLoading(null);
      setEditMode(false);
    }
  }

  async function handleFeedback() {
    if (feedbackRating === 0) return;
    setActionLoading("feedback");
    setActionError(null);
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
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to submit feedback");
    } finally {
      setActionLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center">
        <AlertTriangle className="mb-3 h-10 w-10 text-danger" aria-hidden="true" />
        <p className="font-semibold text-ink">Task not found</p>
        <button
          type="button"
          onClick={onBack}
          className="mt-3 text-sm text-ink-secondary hover:underline"
        >
          Back to list
        </button>
      </div>
    );
  }

  const accentBg = agentColors[task.agent_name] || agentColors.unknown;
  const latestOutput = task.outputs?.length
    ? [...task.outputs].sort((a, b) => b.version - a.version)[0]
    : null;

  const canReview = ["completed", "pending_review", "pending"].includes(task.status);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-line px-5 py-3">
        <button
          type="button"
          onClick={onBack}
          aria-label="Back to list"
          className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted lg:hidden"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
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
          <p className="truncate text-sm font-semibold text-ink">{task.title}</p>
          <p className="text-xs text-ink-secondary">
            {task.agent_display_name} · {formatDate(task.created_at)}
          </p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {/* Description */}
        {task.description && (
          <div>
            <p className="mb-1 text-xs font-semibold text-ink-secondary">
              Description
            </p>
            <p className="text-sm text-ink">{task.description}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Priority", value: (priorityLabels[task.priority] ?? { label: "Low", color: "" }).label },
            { label: "Attempts", value: String(task.attempts) },
            { label: "Tokens", value: task.tokens_used ? task.tokens_used.toLocaleString() : "—" },
            {
              label: "Cost",
              value: task.cost_usd != null ? `$${task.cost_usd.toFixed(4)}` : "—",
            },
          ].map((m) => (
            <div key={m.label} className="rounded-control bg-surface-muted px-3 py-2">
              <p className="mb-0.5 text-[10px] text-ink-secondary">{m.label}</p>
              <p className="text-sm font-semibold text-ink">{m.value}</p>
            </div>
          ))}
        </div>

        {/* Error */}
        {task.error_message && (
          <div className="rounded-control border border-danger/20 bg-danger-soft px-4 py-3">
            <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-danger">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Error
            </p>
            <p className="font-mono text-xs text-danger">{task.error_message}</p>
          </div>
        )}

        {/* Output */}
        {latestOutput && !editMode && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-ink-secondary">
                <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                Output{" "}
                <span className="text-[10px] font-normal text-ink-muted">
                  v{latestOutput.version}
                </span>
              </p>
              {latestOutput.word_count && (
                <span className="text-[10px] text-ink-secondary">
                  {latestOutput.word_count} words
                </span>
              )}
            </div>
            <div className="max-h-[400px] overflow-y-auto whitespace-pre-wrap rounded-card bg-surface-muted p-4 text-sm leading-relaxed text-ink">
              {latestOutput.content || "No content"}
            </div>
            {latestOutput.user_rating && (
              <div className="mt-2 flex items-center gap-2">
                <StarRating value={latestOutput.user_rating} readonly />
                {latestOutput.user_feedback && (
                  <span className="text-xs italic text-ink-secondary">
                    &quot;{latestOutput.user_feedback}&quot;
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Edit mode */}
        {editMode && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-secondary">
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              Edit output
            </p>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              aria-label="Edited output"
              className="h-64 w-full resize-none rounded-control border border-line bg-surface p-4 font-mono text-sm text-ink focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <input
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              placeholder="Notes about your edits (optional)"
              aria-label="Edit notes"
              className="mt-2 w-full rounded-control border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <div className="mt-3 flex gap-2">
              <Button onClick={handleEdit} loading={actionLoading === "edit"}>
                {actionLoading !== "edit" && (
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                )}
                Save and approve
              </Button>
              <Button variant="ghost" onClick={() => setEditMode(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Reject mode */}
        {rejectMode && (
          <div className="rounded-card border border-danger/20 bg-danger-soft p-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-danger">
              <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
              Reject task
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection"
              aria-label="Rejection reason"
              className="h-24 w-full resize-none rounded-control border border-line bg-surface p-3 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <div className="mt-2 flex items-center gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={retryOnReject}
                  onChange={(e) => setRetryOnReject(e.target.checked)}
                  className="h-4 w-4 rounded border-line accent-[#c96442]"
                />
                <RotateCcw className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
                Retry with agent
              </label>
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                variant="danger"
                onClick={handleReject}
                disabled={!rejectReason.trim()}
                loading={actionLoading === "reject"}
              >
                {actionLoading !== "reject" && (
                  <XCircle className="h-4 w-4" aria-hidden="true" />
                )}
                Reject
              </Button>
              <Button variant="ghost" onClick={() => setRejectMode(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Feedback mode */}
        {feedbackMode && (
          <div className="rounded-card border border-line bg-surface-muted p-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-secondary">
              <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
              Leave feedback
            </p>
            <div className="mb-3">
              <p className="mb-1 text-xs text-ink-secondary">Rating</p>
              <StarRating value={feedbackRating} onChange={setFeedbackRating} />
            </div>
            <textarea
              value={feedbackComments}
              onChange={(e) => setFeedbackComments(e.target.value)}
              placeholder="Comments (optional)"
              aria-label="Feedback comments"
              className="h-20 w-full resize-none rounded-control border border-line bg-surface p-3 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <div className="mt-3 flex gap-2">
              <Button
                onClick={handleFeedback}
                disabled={feedbackRating === 0}
                loading={actionLoading === "feedback"}
              >
                {actionLoading !== "feedback" && (
                  <Star className="h-4 w-4" aria-hidden="true" />
                )}
                Submit
              </Button>
              <Button variant="ghost" onClick={() => setFeedbackMode(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Approval notes */}
        {task.approval_notes && (
          <div className="rounded-card bg-surface-muted px-4 py-3">
            <p className="mb-1 text-xs font-semibold text-ink-secondary">
              Review notes
            </p>
            <p className="text-sm text-ink">{task.approval_notes}</p>
          </div>
        )}

        {/* Output version history */}
        {task.outputs.length > 1 && (
          <div>
            <p className="mb-2 text-xs font-semibold text-ink-secondary">
              Version history
            </p>
            <div className="space-y-1">
              {[...task.outputs]
                .sort((a, b) => b.version - a.version)
                .map((o) => (
                  <div
                    key={o.id}
                    className="flex items-center justify-between rounded-control bg-surface-muted px-3 py-2 text-xs"
                  >
                    <span className="font-medium text-ink">v{o.version}</span>
                    <span className="text-ink-secondary">
                      {o.word_count} words · {formatDate(o.created_at)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Action bar */}
      {actionError && (
        <div className="mx-5 mb-2 rounded-control border border-danger/20 bg-danger-soft p-3">
          <p className="flex items-center gap-1.5 text-xs text-danger">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {actionError}
          </p>
        </div>
      )}
      {canReview && !editMode && !rejectMode && !feedbackMode && (
        <div className="flex items-center gap-2 border-t border-line bg-surface px-5 py-3">
          <button
            type="button"
            onClick={handleApprove}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 rounded-control bg-success px-4 py-2 text-sm font-medium text-white transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
          >
            {actionLoading === "approve" ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <ThumbsUp className="h-4 w-4" aria-hidden="true" />
            )}
            Approve
          </button>
          <button
            type="button"
            onClick={() => {
              setRejectMode(true);
              setEditMode(false);
              setFeedbackMode(false);
            }}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 rounded-control border border-danger/30 px-4 py-2 text-sm font-medium text-danger transition-colors duration-150 hover:bg-danger-soft disabled:opacity-50"
          >
            <ThumbsDown className="h-4 w-4" aria-hidden="true" />
            Reject
          </button>
          {latestOutput && (
            <button
              type="button"
              onClick={() => {
                setEditMode(true);
                setRejectMode(false);
                setFeedbackMode(false);
              }}
              disabled={!!actionLoading}
              className="inline-flex items-center gap-1.5 rounded-control border border-line px-4 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:bg-surface-muted disabled:opacity-50"
            >
              <Pencil className="h-4 w-4" aria-hidden="true" />
              Edit
            </button>
          )}
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => {
              setFeedbackMode(true);
              setEditMode(false);
              setRejectMode(false);
            }}
            disabled={!!actionLoading}
            className="inline-flex items-center gap-1.5 rounded-control px-3 py-2 text-sm font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-muted disabled:opacity-50"
          >
            <MessageSquare className="h-4 w-4" aria-hidden="true" />
            Feedback
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Main page ───────────────────────────────────────── */
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
    <div className="space-y-8">
      <PageHeader
        title="Tasks"
        description="Review, approve, and edit agent outputs"
        actions={
          <button
            type="button"
            onClick={fetchTasks}
            className="rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted"
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshCw className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </button>
        }
      />

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[
            { label: "Pending", value: stats.pending_review, icon: Eye, iconColor: "text-ink-secondary bg-surface-muted" },
            { label: "Approved", value: stats.approved_today, icon: ThumbsUp, iconColor: "text-success bg-success-soft" },
            { label: "Rejected", value: stats.rejected_today, icon: ThumbsDown, iconColor: "text-danger bg-danger-soft" },
            { label: "Edited", value: stats.edited_today, icon: Pencil, iconColor: "text-ink-secondary bg-surface-muted" },
            { label: "Total", value: stats.total_tasks, icon: ListTodo, iconColor: "text-ink-secondary bg-surface-muted" },
            {
              label: "Avg rating",
              value: stats.avg_rating ? stats.avg_rating.toFixed(1) : "—",
              icon: Star,
              iconColor: "text-warning bg-warning-soft",
            },
          ].map((s) => (
            <Card key={s.label} className="flex items-center gap-2.5 p-3">
              <div className={clsx("rounded-md p-2", s.iconColor)}>
                <s.icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <div>
                <p className="text-lg font-semibold leading-tight tabular-nums text-ink">{s.value}</p>
                <p className="text-[10px] text-ink-secondary">{s.label}</p>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Main content — list + detail split */}
      <Card className="flex min-h-[400px] overflow-hidden sm:min-h-[600px]">
        {/* Task list panel */}
        <div
          className={clsx(
            "flex w-full shrink-0 flex-col border-line lg:w-[380px] lg:border-r",
            selectedId && "hidden lg:flex"
          )}
        >
          {/* Filters */}
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <div className="relative flex-1">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
                className="w-full cursor-pointer appearance-none rounded-control border border-line bg-surface py-1.5 pl-7 pr-6 text-xs text-ink"
              >
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="pending_review">Needs review</option>
                <option value="completed">Completed</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="failed">Failed</option>
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
            <button
              type="button"
              onClick={() => setNeedsReview(!needsReview)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-control border px-3 py-1.5 text-xs font-medium transition-colors duration-150",
                needsReview
                  ? "border-warning/30 bg-warning-soft text-warning"
                  : "border-line text-ink-secondary hover:bg-surface-muted"
              )}
            >
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Needs review
            </button>
          </div>

          {/* Task list */}
          <div className="flex-1 divide-y divide-line-subtle overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
              </div>
            ) : tasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-6 py-20 text-center">
                <ListTodo className="mb-4 h-10 w-10 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
                <h3 className="mb-1 font-serif text-lg font-semibold text-ink">No tasks found</h3>
                <p className="max-w-xs text-sm text-ink-secondary">
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
            <div className="border-t border-line px-4 py-2 text-xs text-ink-secondary">
              Showing {tasks.length} of {total} tasks
            </div>
          )}
        </div>

        {/* Detail panel */}
        <div
          className={clsx(
            "min-w-0 flex-1",
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
            <div className="flex h-full flex-col items-center justify-center p-8 text-center">
              <FileText className="mb-4 h-12 w-12 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
              <h3 className="mb-1 font-serif text-lg font-semibold text-ink">Select a task</h3>
              <p className="max-w-sm text-sm text-ink-secondary">
                Choose a task from the list to review its output, approve, edit,
                or reject it.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
