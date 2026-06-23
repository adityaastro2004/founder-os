"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApi } from "@/lib/use-api";
import { n8nEditorUrl } from "@/lib/n8n";
import {
  Workflow as WorkflowIcon,
  Play,
  Loader2,
  RefreshCw,
  ExternalLink,
  Clock,
  CalendarClock,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  CircleDot,
  Plus,
  X,
  Sparkles,
} from "lucide-react";
import { clsx } from "clsx";
import {
  type Workflow,
  formatRelative,
  successRatio,
} from "./types";

/* ── Run-now button (per-row, optimistic-safe) ─────────── */
function RunNowButton({
  workflowId,
  onRan,
}: {
  workflowId: string;
  onRan: () => void;
}) {
  const api = useApi();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ranAt, setRanAt] = useState<number | null>(null);

  async function handleRun(e: React.MouseEvent) {
    // Row is wrapped in a Link — don't navigate when clicking "Run now".
    e.preventDefault();
    e.stopPropagation();
    setLoading(true);
    setError(null);
    try {
      await api(`/api/workflows/${workflowId}/run`, { method: "POST" });
      setRanAt(Date.now());
      onRan();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleRun}
        disabled={loading}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
        title="Trigger this workflow now"
      >
        {loading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : ranAt ? (
          <CheckCircle2 className="w-3.5 h-3.5" />
        ) : (
          <Play className="w-3.5 h-3.5" />
        )}
        {loading ? "Starting…" : ranAt ? "Started" : "Run now"}
      </button>
      {error && (
        <span className="text-[10px] text-[var(--color-danger)] flex items-center gap-1 max-w-[180px] text-right">
          <AlertTriangle className="w-3 h-3 shrink-0" />
          {error}
        </span>
      )}
    </div>
  );
}

/* ── Workflow row ───────────────────────────────────────── */
function WorkflowCard({ wf, onRan }: { wf: Workflow; onRan: () => void }) {
  const editorUrl = n8nEditorUrl(wf.n8n_workflow_id);

  return (
    <Link
      href={`/dashboard/workflows/${wf.id}`}
      className="block bg-white rounded-lg border border-[var(--color-border-subtle)] p-5 hover:border-[var(--color-border)] hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="w-9 h-9 rounded-md bg-[var(--color-surface-muted)] flex items-center justify-center shrink-0">
            <WorkflowIcon className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
              <p className="text-sm font-semibold truncate">{wf.name}</p>
              {/* Active / paused */}
              <span
                className={clsx(
                  "inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                  wf.is_active
                    ? "text-[var(--color-success)] bg-[var(--color-success)]/5"
                    : "text-[var(--color-text-muted)] bg-[var(--color-surface-muted)]"
                )}
              >
                <CircleDot className="w-2.5 h-2.5" />
                {wf.is_active ? "Active" : "Paused"}
              </span>
              {/* Schedule */}
              {wf.is_scheduled && (
                <span
                  className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full text-[var(--color-text-secondary)] bg-[var(--color-surface-muted)] font-mono"
                  title={wf.schedule_cron || "Scheduled"}
                >
                  <CalendarClock className="w-2.5 h-2.5" />
                  {wf.schedule_cron || "Scheduled"}
                </span>
              )}
            </div>
            {wf.description && (
              <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2">
                {wf.description}
              </p>
            )}
            <div className="flex items-center gap-3 mt-2 text-[11px] text-[var(--color-text-muted)]">
              <span className="inline-flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Last run {formatRelative(wf.last_run_at)}
              </span>
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                {successRatio(wf.total_runs, wf.successful_runs)} success
                <span className="text-[var(--color-text-muted)]">
                  ({wf.successful_runs}/{wf.total_runs})
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {editorUrl && (
            <a
              href={editorUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] transition-colors"
              title="Open in the n8n editor"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Edit in n8n
            </a>
          )}
          <RunNowButton workflowId={wf.id} onRan={onRan} />
          <ChevronRight className="w-4 h-4 text-[var(--color-text-muted)]" />
        </div>
      </div>
    </Link>
  );
}

/* ── Page ───────────────────────────────────────────────── */
export default function WorkflowsPage() {
  const api = useApi();
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [draft, setDraft] = useState("");

  /* Hand the description to the Orchestrator in chat, which generates the
     automation. Stash it for the chat page to prefill on mount. */
  function startAutomation() {
    const text = draft.trim();
    if (!text) return;
    sessionStorage.setItem("fos-pending-chat-prompt", text);
    router.push("/dashboard/chat");
  }

  const fetchWorkflows = useCallback(async () => {
    setError(null);
    try {
      const data = await api("/api/workflows");
      // Tolerate either a bare list or an enveloped { workflows: [...] }.
      const list: Workflow[] = Array.isArray(data)
        ? data
        : data?.workflows ?? [];
      setWorkflows(list);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't load your workflows"
      );
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Automations</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Automations your AI team runs for you — view, run, and inspect them
            here.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={fetchWorkflows}
            className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-[var(--color-text-secondary)]" />
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add automation
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 rounded-lg bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[var(--color-danger)] shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-[var(--color-danger)]">
              {error}
            </p>
            <button
              onClick={fetchWorkflows}
              className="mt-1 text-xs text-[var(--color-text-secondary)] hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
        </div>
      ) : !error && workflows.length === 0 ? (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-12 flex flex-col items-center justify-center text-center">
          <WorkflowIcon className="w-12 h-12 text-[var(--color-text-muted)] mb-4" />
          <h2 className="text-lg font-semibold mb-2">No automations yet</h2>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-sm mb-5">
            Describe something recurring — like &quot;every Monday, prep my
            standup&quot; — and the Orchestrator will build an automation that
            shows up here.
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add automation
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {workflows.map((wf) => (
            <WorkflowCard key={wf.id} wf={wf} onRan={fetchWorkflows} />
          ))}
        </div>
      )}

      {/* Add-automation modal: describe it → hand off to the Orchestrator. */}
      {showAdd && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setShowAdd(false)}
        >
          <div
            className="w-full max-w-lg bg-white rounded-xl border border-[var(--color-border)] shadow-lg p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 mb-1">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[var(--color-accent)]" />
                <h2 className="text-lg font-semibold">New automation</h2>
              </div>
              <button
                onClick={() => setShowAdd(false)}
                className="p-1 rounded-md hover:bg-[var(--color-surface-muted)] transition-colors"
                title="Close"
              >
                <X className="w-4 h-4 text-[var(--color-text-secondary)]" />
              </button>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-4">
              Describe what should happen, when, and which specialist handles it.
              The Orchestrator turns this into a runnable automation.
            </p>
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter")
                  startAutomation();
              }}
              rows={4}
              placeholder="e.g. Every Monday at 8am, summarise last week's support tickets and email me the highlights."
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
            />
            <div className="flex items-center justify-end gap-2 mt-4">
              <button
                onClick={() => setShowAdd(false)}
                className="px-4 py-2.5 text-sm font-medium rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={startAutomation}
                disabled={!draft.trim()}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
              >
                <Sparkles className="w-4 h-4" />
                Continue in chat
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
