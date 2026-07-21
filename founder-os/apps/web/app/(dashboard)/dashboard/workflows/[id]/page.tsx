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
import { Card, Button } from "@/app/_components/ui";

/* ── Run status badge ───────────────────────────────────── */
function RunStatusBadge({ status }: { status: string }) {
  const cfg = runStatus(status);
  const Icon = cfg.icon;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        cfg.color
      )}
    >
      <Icon className={clsx("h-3 w-3", cfg.spin && "animate-spin")} aria-hidden="true" />
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
      <div className="flex shrink-0 flex-col items-center">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-muted text-[11px] font-semibold text-ink-secondary">
          {index + 1}
        </div>
      </div>
      <div className="min-w-0 flex-1 pb-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-medium text-ink-secondary">
            <Icon className="h-2.5 w-2.5" aria-hidden="true" />
            {step.type}
          </span>
          {step.agent && (
            <span className="text-[11px] font-medium text-ink-secondary">
              {step.agent}
            </span>
          )}
          {step.tool && (
            <span className="font-mono text-[11px] text-ink-secondary">
              {step.tool}
            </span>
          )}
        </div>
        {step.instruction && (
          <p className="text-xs text-ink">{step.instruction}</p>
        )}
        {step.arguments && Object.keys(step.arguments).length > 0 && (
          <pre className="mt-1 overflow-x-auto rounded-md bg-surface-muted p-2 font-mono text-[10px] text-ink-secondary">
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
    <div className="space-y-3 border-t border-line bg-surface-muted/40 px-5 py-4">
      {loading && (
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          Loading run details
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
            className="rounded-control border border-line bg-surface px-3 py-2"
          >
            <p className="mb-0.5 text-[10px] text-ink-secondary">{m.label}</p>
            <p className="truncate text-xs font-medium text-ink" title={m.value}>
              {m.value}
            </p>
          </div>
        ))}
      </div>

      {full.output_summary && (
        <div>
          <p className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-ink-secondary">
            <FileText className="h-3 w-3" aria-hidden="true" /> Result
          </p>
          <div className="max-h-[280px] overflow-y-auto whitespace-pre-wrap rounded-control border border-line bg-surface p-3 text-xs leading-relaxed text-ink">
            {full.output_summary}
          </div>
        </div>
      )}

      {full.error_message && (
        <div className="rounded-control border border-danger/20 bg-danger-soft px-3 py-2">
          <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold text-danger">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" /> Error
          </p>
          <p className="whitespace-pre-wrap font-mono text-xs text-danger">
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
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors duration-150 hover:bg-surface-muted/60"
      >
        <RunStatusBadge status={run.status} />
        <span className="text-xs text-ink-secondary">
          {run.trigger_type || "—"}
        </span>
        <span className="text-xs text-ink-secondary">
          {formatRelative(run.started_at)}
        </span>
        <div className="flex-1" />
        {run.error_message && (
          <span className="hidden max-w-[200px] truncate text-[11px] text-danger sm:inline">
            {run.error_message}
          </span>
        )}
        <ChevronRight
          className={clsx(
            "h-4 w-4 text-ink-muted transition-transform duration-150",
            open && "rotate-90"
          )}
          aria-hidden="true"
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

  const backLink = (
    <Link
      href="/dashboard/workflows"
      className="inline-flex items-center gap-1.5 text-sm text-ink-secondary transition-colors duration-150 hover:text-ink"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Automations
    </Link>
  );

  /* ── Loading ── */
  if (loading) {
    return (
      <div className="space-y-8">
        {backLink}
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
        </div>
      </div>
    );
  }

  /* ── Error / not found ── */
  if (error || !workflow) {
    return (
      <div className="space-y-8">
        {backLink}
        <Card className="flex flex-col items-center justify-center p-12 text-center">
          <AlertTriangle className="mb-4 h-10 w-10 text-danger" aria-hidden="true" />
          <h2 className="mb-2 font-serif text-lg font-semibold text-ink">
            {error || "Workflow not found"}
          </h2>
          <button
            type="button"
            onClick={fetchAll}
            className="mt-1 text-sm text-ink-secondary hover:underline"
          >
            Try again
          </button>
        </Card>
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
      {backLink}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink">
              {workflow.name}
            </h1>
            <span
              className={clsx(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                workflow.is_active
                  ? "bg-success-soft text-success"
                  : "bg-surface-muted text-ink-secondary"
              )}
            >
              <CircleDot className="h-2.5 w-2.5" aria-hidden="true" />
              {workflow.is_active ? "Active" : "Paused"}
            </span>
          </div>
          {workflow.description && (
            <p className="mt-1 text-sm text-ink-secondary">
              {workflow.description}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {editorUrl && (
            <a
              href={editorUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-control border border-line px-4 py-2 text-sm font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-muted"
              title="Open in the n8n editor"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              View / edit in n8n
            </a>
          )}
          <Button onClick={handleRunNow} loading={running}>
            {!running && <Play className="h-4 w-4" aria-hidden="true" />}
            {running ? "Starting" : "Run now"}
          </Button>
        </div>
      </div>

      {runError && (
        <div className="rounded-control border border-danger/20 bg-danger-soft p-3">
          <p className="flex items-center gap-1.5 text-xs text-danger">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {runError}
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
          <Card key={s.label} className="flex items-center gap-2.5 p-3">
            <div className="rounded-md bg-surface-muted p-2 text-ink-secondary">
              <s.icon className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p
                className={clsx(
                  "truncate text-sm font-semibold leading-tight text-ink",
                  s.mono && "font-mono text-xs"
                )}
                title={s.value}
              >
                {s.value}
              </p>
              <p className="text-[10px] text-ink-secondary">{s.label}</p>
            </div>
          </Card>
        ))}
      </div>

      {/* Steps (read-only IR) */}
      <Card className="p-5">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink">
          <Bot className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          What this workflow does
        </h2>
        <p className="mb-4 text-xs text-ink-secondary">
          The trigger and ordered steps the AI generated. To change them, use
          &quot;View / edit in n8n&quot; above.
        </p>

        {/* Trigger */}
        {trigger && (
          <div className="mb-4 inline-flex items-center gap-2 rounded-control bg-surface-muted px-3 py-1.5 text-xs">
            {trigger.type === "cron" ? (
              <CalendarClock className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
            ) : (
              <Zap className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
            )}
            <span className="font-medium capitalize text-ink">
              {trigger.type} trigger
            </span>
            {trigger.cron && (
              <span className="font-mono text-ink-secondary">
                {trigger.cron}
                {trigger.timezone ? ` · ${trigger.timezone}` : ""}
              </span>
            )}
          </div>
        )}

        {steps.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            No steps available for this workflow.
          </p>
        ) : (
          <div className="space-y-3">
            {steps.map((step, i) => (
              <StepRow key={step.id || i} step={step} index={i} />
            ))}
          </div>
        )}
      </Card>

      {/* Run history */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <History className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
            Run history
            <span className="text-xs font-normal text-ink-secondary">
              ({runs.length})
            </span>
          </h2>
          <button
            type="button"
            onClick={fetchAll}
            className="rounded-control p-1.5 transition-colors duration-150 hover:bg-surface-muted"
            title="Refresh runs"
            aria-label="Refresh runs"
          >
            <RefreshCw className="h-3.5 w-3.5 text-ink-secondary" aria-hidden="true" />
          </button>
        </div>
        {runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
            <History className="mb-3 h-9 w-9 text-ink-muted" strokeWidth={1.5} aria-hidden="true" />
            <p className="mb-1 text-sm font-medium text-ink">No runs yet</p>
            <p className="max-w-xs text-xs text-ink-secondary">
              Trigger this workflow with &quot;Run now&quot; or wait for its
              schedule — each run will appear here.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-line-subtle">
            {runs.map((run) => (
              <RunRow key={run.id} run={run} api={api} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
