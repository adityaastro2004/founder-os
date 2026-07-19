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
  Sparkles,
} from "lucide-react";
import { clsx } from "clsx";
import {
  type Workflow,
  formatRelative,
  successRatio,
} from "./types";
import {
  PageHeader,
  Button,
  EmptyState,
  Textarea,
  Dialog,
} from "@/app/_components/ui";

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
        type="button"
        onClick={handleRun}
        disabled={loading}
        className="inline-flex items-center gap-1.5 rounded-control bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors duration-150 hover:bg-accent-hover disabled:opacity-50"
        title="Trigger this workflow now"
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        ) : ranAt ? (
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {loading ? "Starting" : ranAt ? "Started" : "Run now"}
      </button>
      {error && (
        <span className="flex max-w-[180px] items-center gap-1 text-right text-[10px] text-danger">
          <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
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
      className="block rounded-card border border-line bg-surface p-5 transition-colors duration-150 hover:bg-surface-muted/40"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface-muted">
            <WorkflowIcon className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex flex-wrap items-center gap-2">
              <p className="truncate text-sm font-semibold text-ink">{wf.name}</p>
              {/* Active / paused */}
              <span
                className={clsx(
                  "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                  wf.is_active
                    ? "bg-success-soft text-success"
                    : "bg-surface-muted text-ink-secondary"
                )}
              >
                <CircleDot className="h-2.5 w-2.5" aria-hidden="true" />
                {wf.is_active ? "Active" : "Paused"}
              </span>
              {/* Schedule */}
              {wf.is_scheduled && (
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-ink-secondary"
                  title={wf.schedule_cron || "Scheduled"}
                >
                  <CalendarClock className="h-2.5 w-2.5" aria-hidden="true" />
                  {wf.schedule_cron || "Scheduled"}
                </span>
              )}
            </div>
            {wf.description && (
              <p className="line-clamp-2 text-xs text-ink-secondary">
                {wf.description}
              </p>
            )}
            <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-secondary">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" aria-hidden="true" />
                Last run {formatRelative(wf.last_run_at)}
              </span>
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                {successRatio(wf.total_runs, wf.successful_runs)} success
                <span>
                  ({wf.successful_runs}/{wf.total_runs})
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-2">
          {editorUrl && (
            <a
              href={editorUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-xs font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-muted"
              title="Open in the n8n editor"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              Edit in n8n
            </a>
          )}
          <RunNowButton workflowId={wf.id} onRan={onRan} />
          <ChevronRight className="h-4 w-4 text-ink-muted" aria-hidden="true" />
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
      <PageHeader
        title="Automations"
        description="Automations your AI team runs for you — view, run, and inspect them here"
        actions={
          <>
            <button
              type="button"
              onClick={fetchWorkflows}
              className="rounded-control p-2 transition-colors duration-150 hover:bg-surface-muted"
              title="Refresh"
              aria-label="Refresh"
            >
              <RefreshCw className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
            </button>
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add automation
            </Button>
          </>
        }
      />

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-control border border-danger/20 bg-danger-soft p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-danger">{error}</p>
            <button
              type="button"
              onClick={fetchWorkflows}
              className="mt-1 text-xs text-ink-secondary hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
        </div>
      ) : !error && workflows.length === 0 ? (
        <EmptyState
          icon={WorkflowIcon}
          title="No automations yet"
          body={`Describe something recurring — like "every Monday, prep my standup" — and the Orchestrator will build an automation that shows up here.`}
          action={
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add automation
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {workflows.map((wf) => (
            <WorkflowCard key={wf.id} wf={wf} onRan={fetchWorkflows} />
          ))}
        </div>
      )}

      {/* Add-automation modal: describe it → hand off to the Orchestrator. */}
      <Dialog
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title="New automation"
        className="max-w-lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button onClick={startAutomation} disabled={!draft.trim()}>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Continue in chat
            </Button>
          </>
        }
      >
        <p className="mb-4 text-sm text-ink-secondary">
          Describe what should happen, when, and which specialist handles it.
          The Orchestrator turns this into a runnable automation.
        </p>
        <Textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter")
              startAutomation();
          }}
          rows={4}
          aria-label="Automation description"
          placeholder="e.g. Every Monday at 8am, summarise last week's support tickets and email me the highlights."
        />
      </Dialog>
    </div>
  );
}
