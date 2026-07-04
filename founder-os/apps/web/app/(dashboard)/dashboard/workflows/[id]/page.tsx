"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useApi } from "@/lib/use-api";
import { n8nEditorUrl } from "@/lib/n8n";
import {
  ArrowLeft,
  Play,
  Loader2,
  RefreshCw,
  ExternalLink,
  Clock,
  CalendarClock,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  Bot,
  Wrench,
  Zap,
  CircleDot,
  History,
  FileText,
} from "lucide-react";
import { clsx } from "clsx";
import {
  type WorkflowDetail,
  type WorkflowRun,
  type WorkflowStep,
  runStatus,
  formatRelative,
  formatExact,
  successRatio,
} from "../types";

/* ── Run status badge ───────────────────────────────────── */
function RunStatusBadge({ status }: { status: string }) {
  const cfg = runStatus(status);
  const Icon = cfg.icon;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium",
        cfg.color
      )}
    >
      <Icon className={clsx("w-3 h-3", cfg.spin && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

/* ── Read-only IR step ──────────────────────────────────── */
function StepRow({ step, index }: { step: WorkflowStep; index: number }) {
  const isAction = step.type === "action";
  const Icon = isAction ? Wrench : Bot;
  return (
    <div className="flex items-start gap-3">
      {/* Connector + index */}
      <div className="flex flex-col items-center shrink-0">
        <div className="w-7 h-7 rounded-md bg-[var(--color-surface-muted)] flex items-center justify-center text-[11px] font-semibold text-[var(--color-text-secondary)]">
          {index + 1}
        </div>
      </div>
      <div className="flex-1 min-w-0 pb-1">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] uppercase tracking-wider">
            <Icon className="w-2.5 h-2.5" />
            {step.type}
          </span>
          {step.agent && (
            <span className="text-[11px] font-medium text-[var(--color-text-secondary)]">
              {step.agent}
            </span>
          )}
          {step.tool && (
            <span className="text-[11px] font-mono text-[var(--color-text-muted)]">
              {step.tool}
            </span>
          )}
        </div>
        {step.instruction && (
          <p className="text-xs text-[var(--color-text-primary)]">
            {step.instruction}
          </p>
        )}
        {step.arguments && Object.keys(step.arguments).length > 0 && (
          <pre className="mt-1 text-[10px] font-mono text-[var(--color-text-muted)] bg-[var(--color-surface-muted)] rounded-md p-2 overflow-x-auto">
            {JSON.stringify(step.arguments, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

/* ── Single-run detail (inline panel) ───────────────────── */
function RunDetail({
  run,
  api,
}: {
  run: WorkflowRun;
  api: ReturnType<typeof useApi>;
}) {
  const [full, setFull] = useState<WorkflowRun>(run);
  const [loading, setLoading] = useState(false);

  // Fetch the richer single-run view; fall back to the list row on failure.
  useEffect(() => {
    let active = true;
    setLoading(true);
    api(`/api/workflows/runs/${run.id}`)
      .then((data: WorkflowRun) => {
        if (active && data) setFull(data);
      })
      .catch(() => {
        /* keep the list-row data */
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [run.id, api]);

  return (
    <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-5 py-4 space-y-3">
      {loading && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading run details…
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Trigger", value: full.trigger_type || "—" },
          { label: "Started", value: formatExact(full.started_at) },
          { label: "Completed", value: formatExact(full.completed_at) },
          {
            label: "Steps",
            value: `${full.steps_completed ?? 0} ok · ${full.steps_failed ?? 0} failed`,
          },
        ].map((m) => (
          <div
            key={m.label}
            className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] px-3 py-2"
          >
            <p className="text-[10px] text-[var(--color-text-muted)] mb-0.5">
              {m.label}
            </p>
            <p className="text-xs font-medium truncate" title={m.value}>
              {m.value}
            </p>
          </div>
        ))}
      </div>

      {full.output_summary && (
        <div>
          <p className="text-[10px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-1 flex items-center gap-1.5">
            <FileText className="w-3 h-3" /> Result
          </p>
          <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-3 text-xs whitespace-pre-wrap leading-relaxed max-h-[280px] overflow-y-auto">
            {full.output_summary}
          </div>
        </div>
      )}

      {full.error_message && (
        <div className="bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20 rounded-lg px-3 py-2">
          <p className="text-[10px] font-semibold text-[var(--color-danger)] mb-1 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Error
          </p>
          <p className="text-xs text-[var(--color-danger)] font-mono whitespace-pre-wrap">
            {full.error_message}
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Run history row (expandable) ───────────────────────── */
function RunRow({
  run,
  api,
}: {
  run: WorkflowRun;
  api: ReturnType<typeof useApi>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-[var(--color-surface-muted)] transition-colors"
      >
        <RunStatusBadge status={run.status} />
        <span className="text-xs text-[var(--color-text-secondary)]">
          {run.trigger_type || "—"}
        </span>
        <span className="text-xs text-[var(--color-text-muted)]">
          {formatRelative(run.started_at)}
        </span>
        <div className="flex-1" />
        {run.error_message && (
          <span className="text-[11px] text-[var(--color-danger)] truncate max-w-[200px] hidden sm:inline">
            {run.error_message}
          </span>
        )}
        <ChevronRight
          className={clsx(
            "w-4 h-4 text-[var(--color-text-muted)] transition-transform",
            open && "rotate-90"
          )}
        />
      </button>
      {open && <RunDetail run={run} api={api} />}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────── */
export default function WorkflowDetailPage() {
  const api = useApi();
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [wf, runData] = await Promise.all([
        api(`/api/workflows/${id}`),
        api(`/api/workflows/${id}/runs`).catch(() => null),
      ]);
      setWorkflow(wf);
      const list: WorkflowRun[] = Array.isArray(runData)
        ? runData
        : runData?.runs ?? [];
      setRuns(list);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't load this workflow"
      );
    } finally {
      setLoading(false);
    }
  }, [api, id]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  async function handleRunNow() {
    setRunning(true);
    setRunError(null);
    try {
      await api(`/api/workflows/${id}/run`, { method: "POST" });
      // Give the backend a beat to create the execution row, then refresh.
      setTimeout(fetchAll, 600);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setRunning(false);
    }
  }

  /* ── Loading ── */
  if (loading) {
    return (
      <div className="space-y-8">
        <Link
          href="/dashboard/workflows"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Workflows
        </Link>
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
        </div>
      </div>
    );
  }

  /* ── Error / not found ── */
  if (error || !workflow) {
    return (
      <div className="space-y-8">
        <Link
          href="/dashboard/workflows"
          className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Workflows
        </Link>
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-12 flex flex-col items-center justify-center text-center">
          <AlertTriangle className="w-12 h-12 text-[var(--color-danger)] mb-4" />
          <h2 className="text-lg font-semibold mb-2">
            {error || "Workflow not found"}
          </h2>
          <button
            onClick={fetchAll}
            className="mt-1 text-sm text-[var(--color-text-secondary)] hover:underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const editorUrl = n8nEditorUrl(workflow.n8n_workflow_id);
  const ir = workflow.steps;
  const steps = ir?.steps ?? [];
  const trigger = ir?.trigger;

  return (
    <div className="space-y-8">
      {/* Back */}
      <Link
        href="/dashboard/workflows"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Workflows
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight">
              {workflow.name}
            </h1>
            <span
              className={clsx(
                "inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full",
                workflow.is_active
                  ? "text-[var(--color-success)] bg-[var(--color-success)]/5"
                  : "text-[var(--color-text-muted)] bg-[var(--color-surface-muted)]"
              )}
            >
              <CircleDot className="w-2.5 h-2.5" />
              {workflow.is_active ? "Active" : "Paused"}
            </span>
          </div>
          {workflow.description && (
            <p className="text-[var(--color-text-secondary)] mt-1">
              {workflow.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {editorUrl && (
            <a
              href={editorUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] transition-colors"
              title="Open in the n8n editor"
            >
              <ExternalLink className="w-4 h-4" />
              View / Edit in n8n
            </a>
          )}
          <button
            onClick={handleRunNow}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
          >
            {running ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {running ? "Starting…" : "Run now"}
          </button>
        </div>
      </div>

      {runError && (
        <div className="p-3 rounded-lg bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20">
          <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            {runError}
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          {
            label: "Schedule",
            value: workflow.is_scheduled
              ? workflow.schedule_cron || "Scheduled"
              : "Manual",
            icon: workflow.is_scheduled ? CalendarClock : Zap,
            mono: workflow.is_scheduled,
          },
          {
            label: "Last run",
            value: formatRelative(workflow.last_run_at),
            icon: Clock,
          },
          {
            label: "Total runs",
            value: String(workflow.total_runs),
            icon: History,
          },
          {
            label: "Success rate",
            value: successRatio(
              workflow.total_runs,
              workflow.successful_runs
            ),
            icon: CheckCircle2,
          },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-3 flex items-center gap-2.5"
          >
            <div className="p-2 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
              <s.icon className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <p
                className={clsx(
                  "text-sm font-semibold leading-tight truncate",
                  s.mono && "font-mono text-xs"
                )}
                title={s.value}
              >
                {s.value}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                {s.label}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Steps (read-only IR) */}
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
        <h2 className="text-sm font-semibold mb-1 flex items-center gap-2">
          <Bot className="w-4 h-4 text-[var(--color-text-secondary)]" />
          What this workflow does
        </h2>
        <p className="text-xs text-[var(--color-text-secondary)] mb-4">
          The trigger and ordered steps the AI generated. To change them, use
          &quot;View / Edit in n8n&quot; above.
        </p>

        {/* Trigger */}
        {trigger && (
          <div className="mb-4 inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-[var(--color-surface-muted)]">
            {trigger.type === "cron" ? (
              <CalendarClock className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
            ) : (
              <Zap className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
            )}
            <span className="font-medium capitalize">
              {trigger.type} trigger
            </span>
            {trigger.cron && (
              <span className="font-mono text-[var(--color-text-muted)]">
                {trigger.cron}
                {trigger.timezone ? ` · ${trigger.timezone}` : ""}
              </span>
            )}
          </div>
        )}

        {steps.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            No steps available for this workflow.
          </p>
        ) : (
          <div className="space-y-3">
            {steps.map((step, i) => (
              <StepRow key={step.id || i} step={step} index={i} />
            ))}
          </div>
        )}
      </div>

      {/* Run history */}
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-border)] flex items-center justify-between">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <History className="w-4 h-4 text-[var(--color-text-secondary)]" />
            Run history
            <span className="text-xs font-normal text-[var(--color-text-muted)]">
              ({runs.length})
            </span>
          </h2>
          <button
            onClick={fetchAll}
            className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] transition-colors"
            title="Refresh runs"
          >
            <RefreshCw className="w-3.5 h-3.5 text-[var(--color-text-secondary)]" />
          </button>
        </div>
        {runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center px-6">
            <History className="w-10 h-10 text-[var(--color-text-muted)] mb-3" />
            <p className="text-sm font-medium mb-1">No runs yet</p>
            <p className="text-xs text-[var(--color-text-secondary)] max-w-xs">
              Trigger this workflow with &quot;Run now&quot; or wait for its
              schedule — each run will appear here.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[var(--color-border)]">
            {runs.map((run) => (
              <RunRow key={run.id} run={run} api={api} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
