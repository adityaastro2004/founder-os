/**
 * Shared types + presentation helpers for the workflows dashboard (Track I).
 *
 * Built against the ADR-008 API contract (the "API surface" subsection). The
 * backend endpoints are being built in parallel; these shapes mirror the
 * documented contract and tolerate missing/optional fields defensively.
 */

import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Loader2,
  PauseCircle,
} from "lucide-react";

/* ── IR (read-only render) — ADR-008 Contract 1, ir_version 1 ── */
export interface WorkflowTrigger {
  type: string; // "manual" | "cron"
  cron?: string;
  timezone?: string;
}

export interface WorkflowStep {
  id: string;
  type: string; // "agent" | "action"
  agent?: string;
  instruction?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  depends_on?: string[];
}

export interface WorkflowIR {
  ir_version?: number;
  trigger?: WorkflowTrigger;
  steps?: WorkflowStep[];
}

/* ── Workflow (list + detail) — ADR-008 API surface ── */
export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  is_scheduled: boolean;
  schedule_cron: string | null;
  last_run_at: string | null;
  total_runs: number;
  successful_runs: number;
  n8n_workflow_id: string | null;
}

export interface WorkflowDetail extends Workflow {
  steps: WorkflowIR | null;
}

/* ── WorkflowExecution (run history + single run) — ADR-008 ── */
export interface WorkflowRun {
  id: string;
  status: string; // running | completed | failed | awaiting_approval | ...
  trigger_type: string | null; // manual | cron | ...
  started_at: string | null;
  completed_at: string | null;
  steps_completed: number | null;
  steps_failed: number | null;
  output_summary: string | null;
  error_message: string | null;
}

/* ── Run status presentation ── */
export interface RunStatusConfig {
  label: string;
  color: string;
  icon: React.ElementType;
  spin?: boolean;
}

const PENDING_STATUS: RunStatusConfig = {
  label: "Pending",
  color: "text-ink-secondary bg-surface-muted",
  icon: Clock,
};

export const runStatusConfig: Record<string, RunStatusConfig> = {
  running: {
    label: "Running",
    color: "text-ink-secondary bg-surface-muted",
    icon: Loader2,
    spin: true,
  },
  completed: {
    label: "Completed",
    color: "text-success bg-success-soft",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    color: "text-danger bg-danger-soft",
    icon: AlertTriangle,
  },
  awaiting_approval: {
    label: "Awaiting approval",
    color: "text-warning bg-warning-soft",
    icon: PauseCircle,
  },
  cancelled: {
    label: "Cancelled",
    color: "text-ink-secondary bg-surface-muted",
    icon: XCircle,
  },
  pending: PENDING_STATUS,
};

export function runStatus(status: string): RunStatusConfig {
  return (
    runStatusConfig[status] ?? {
      ...PENDING_STATUS,
      label: status || "Unknown",
    }
  );
}

/* ── Time formatting (matches tasks/page.tsx idiom) ── */
export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
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

export function formatExact(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Success ratio as a percentage string, or "—" when there are no runs. */
export function successRatio(total: number, successful: number): string {
  if (!total || total <= 0) return "—";
  return `${Math.round((successful / total) * 100)}%`;
}
