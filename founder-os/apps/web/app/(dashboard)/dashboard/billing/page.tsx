"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import {
  Check,
  CreditCard,
  ExternalLink,
  Loader2,
  Sparkles,
  Zap,
  Crown,
  Building2,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";
import { clsx } from "clsx";
import { PageHeader, Card, Badge } from "@/app/_components/ui";

/* ── Types ─────────────────────────────────────────── */
interface Plan {
  name: string;
  display_name: string | null;
  description: string | null;
  price_monthly_usd: number | null;
  price_yearly_usd: number | null;
  monthly_task_limit: number | null;
  agent_limit: number | null;
  workflow_limit: number | null;
  knowledge_items_limit: number | null;
  team_members_limit: number | null;
  features: string[] | null;
  is_current: boolean;
}

interface BillingStatus {
  subscription_tier: string;
  subscription_status: string;
  monthly_task_limit: number;
  monthly_tasks_used: number;
  trial_ends_at: string | null;
  stripe_customer_id: string | null;
  has_payment_method: boolean;
}

/* ── Plan display config ──────────────────────────── */
const PLAN_CONFIG: Record<
  string,
  {
    icon: React.ElementType;
    popular?: boolean;
  }
> = {
  free: { icon: Zap },
  starter: { icon: Sparkles, popular: true },
  pro: { icon: Crown },
  enterprise: { icon: Building2 },
};

const FEATURE_LABELS: Record<string, string> = {
  basic_agents: "Basic agents",
  all_agents: "All agents",
  manual_workflows: "Manual workflows",
  scheduled_workflows: "Scheduled workflows",
  custom_workflows: "Custom workflows",
  basic_integrations: "Basic integrations",
  advanced_integrations: "Advanced integrations",
  all_integrations: "All integrations",
  email_support: "Email support",
  priority_support: "Priority support",
  dedicated_support: "Dedicated support",
  api_access: "API access",
  white_label: "White-label",
  sla: "SLA guarantee",
};

/* ── Status badge ─────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { tone: "success" | "accent" | "warning" | "danger"; label: string }> = {
    active: { tone: "success", label: "Active" },
    trial: { tone: "accent", label: "Trial" },
    past_due: { tone: "warning", label: "Past due" },
    canceled: { tone: "danger", label: "Canceled" },
  };
  const c = config[status] ?? config.trial!;
  return <Badge tone={c.tone}>{c.label}</Badge>;
}

/* ── Usage bar ────────────────────────────────────── */
function UsageBar({
  used,
  limit,
}: {
  used: number;
  limit: number;
}) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const isHigh = pct > 80;
  const isFull = pct >= 100;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink-secondary">Tasks this month</span>
        <span className={clsx("font-medium tabular-nums text-ink", isFull && "text-danger")}>
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={clsx(
            "h-full rounded-full transition-all duration-500 ease-out",
            isFull ? "bg-danger" : isHigh ? "bg-warning" : "bg-accent"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ── Plan card ────────────────────────────────────── */
function PlanCard({
  plan,
  currentTier,
  onUpgrade,
  loading,
}: {
  plan: Plan;
  currentTier: string;
  onUpgrade: (plan: string) => void;
  loading: boolean;
}) {
  const config = PLAN_CONFIG[plan.name] ?? PLAN_CONFIG.free!;
  const Icon = config.icon;
  const isCurrent = plan.is_current;
  const isFreePlan = plan.name === "free";
  const isDowngrade =
    !isCurrent &&
    (plan.price_monthly_usd || 0) <
      (currentTier === "enterprise" ? 999 : currentTier === "pro" ? 299 : currentTier === "starter" ? 99 : 0);

  return (
    <div
      className={clsx(
        "relative flex flex-col rounded-card border bg-surface p-6 transition-colors duration-150",
        isCurrent
          ? "border-accent ring-1 ring-accent/10"
          : "border-line hover:bg-surface-muted/30"
      )}
    >
      {/* Popular badge */}
      {config.popular && !isCurrent && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="rounded-full bg-accent px-3 py-1 text-[10px] font-semibold text-white">
            Most popular
          </span>
        </div>
      )}

      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-muted">
          <Icon className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
        </div>
        <div>
          <h3 className="font-serif text-sm font-semibold text-ink">
            {plan.display_name || plan.name}
          </h3>
          {isCurrent && (
            <span className="text-[10px] font-medium text-accent-text">
              Current plan
            </span>
          )}
        </div>
      </div>

      {/* Price */}
      <div className="mb-4">
        {isFreePlan ? (
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-semibold tracking-tight text-ink">$0</span>
            <span className="text-sm text-ink-secondary">forever</span>
          </div>
        ) : (
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-semibold tracking-tight text-ink">
              ${plan.price_monthly_usd}
            </span>
            <span className="text-sm text-ink-secondary">/mo</span>
          </div>
        )}
        {plan.price_yearly_usd && !isFreePlan && (
          <p className="mt-1 text-xs text-ink-secondary">
            ${plan.price_yearly_usd}/yr (save{" "}
            {Math.round(
              100 - (plan.price_yearly_usd / ((plan.price_monthly_usd || 1) * 12)) * 100
            )}
            %)
          </p>
        )}
      </div>

      {/* Description */}
      <p className="mb-5 text-sm leading-relaxed text-ink-secondary">
        {plan.description || "—"}
      </p>

      {/* Limits */}
      <div className="mb-6 flex-1 space-y-2.5">
        <LimitRow label="Tasks / month" value={plan.monthly_task_limit} unlimited={(plan.monthly_task_limit ?? 0) > 99999} />
        <LimitRow label="Agents" value={plan.agent_limit} />
        <LimitRow label="Workflows" value={plan.workflow_limit} />
        <LimitRow label="Knowledge items" value={plan.knowledge_items_limit} />
        <LimitRow label="Team members" value={plan.team_members_limit} />
      </div>

      {/* Features */}
      {plan.features && plan.features.length > 0 && (
        <div className="mb-5 border-t border-line-subtle pt-4">
          <p className="mb-2.5 text-[10px] font-medium text-ink-secondary">
            Includes
          </p>
          <ul className="space-y-1.5">
            {plan.features.map((f: string) => (
              <li key={f} className="flex items-center gap-2 text-sm text-ink-secondary">
                <Check className="h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
                {FEATURE_LABELS[f] || f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action button */}
      {isCurrent ? (
        <button
          type="button"
          disabled
          className="w-full cursor-default rounded-control border border-line px-4 py-2.5 text-sm font-medium text-ink-muted"
        >
          Current plan
        </button>
      ) : isFreePlan || isDowngrade ? (
        <button
          type="button"
          disabled
          className="w-full cursor-default rounded-control border border-line px-4 py-2.5 text-sm font-medium text-ink-muted"
        >
          {isDowngrade ? "Downgrade via portal" : "Free"}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => onUpgrade(plan.name)}
          disabled={loading}
          className={clsx(
            "flex w-full items-center justify-center gap-2 rounded-control px-4 py-2.5 text-sm font-medium transition-colors duration-150",
            config.popular
              ? "bg-accent text-white hover:bg-accent-hover"
              : "border border-accent text-accent-text hover:bg-accent-soft/50"
          )}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <>
              Upgrade
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </>
          )}
        </button>
      )}
    </div>
  );
}

function LimitRow({
  label,
  value,
  unlimited,
}: {
  label: string;
  value: number | null | undefined;
  unlimited?: boolean | null;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-ink-secondary">{label}</span>
      <span className="font-medium tabular-nums text-ink">
        {unlimited ? "Unlimited" : value?.toLocaleString() ?? "—"}
      </span>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────── */
export default function BillingPage() {
  const api = useApi();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgradeLoading, setUpgradeLoading] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Check for success/canceled from Stripe redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("success") === "true") {
      setToast({ type: "success", message: "Subscription activated. Welcome aboard." });
      // Clean URL
      window.history.replaceState({}, "", "/dashboard/billing");
    } else if (params.get("canceled") === "true") {
      setToast({ type: "error", message: "Checkout canceled. No charges were made." });
      window.history.replaceState({}, "", "/dashboard/billing");
    }
  }, []);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  const fetchData = useCallback(async () => {
    try {
      const [plansData, statusData] = await Promise.all([
        api("/api/billing/plans").catch(() => []),
        api("/api/billing/status").catch(() => null),
      ]);
      setPlans(plansData);
      if (statusData) setStatus(statusData);
    } catch {
      // API not ready
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleUpgrade = async (planName: string) => {
    setUpgradeLoading(true);
    try {
      const data = await api("/api/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan: planName }),
      });
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to create checkout session";
      setToast({ type: "error", message });
    } finally {
      setUpgradeLoading(false);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data = await api("/api/billing/portal", {
        method: "POST",
      });
      if (data.portal_url) {
        window.location.href = data.portal_url;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to open portal";
      setToast({ type: "error", message });
    } finally {
      setPortalLoading(false);
    }
  };

  const currentTier = status?.subscription_tier || "free";

  return (
    <div className="space-y-8">
      {/* Toast */}
      {toast && (
        <div
          className={clsx(
            "flex items-center gap-3 rounded-control border p-4",
            toast.type === "success"
              ? "border-success/20 bg-success-soft text-success"
              : "border-danger/20 bg-danger-soft text-danger"
          )}
        >
          {toast.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          <p className="flex-1 text-sm font-medium">{toast.message}</p>
          <button
            type="button"
            onClick={() => setToast(null)}
            aria-label="Dismiss"
            className="text-sm opacity-60 hover:opacity-100"
          >
            ×
          </button>
        </div>
      )}

      <PageHeader
        title="Billing"
        description="Manage your subscription and usage"
      />

      {/* Current plan + usage card */}
      {status && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Current plan */}
          <Card className="p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-muted">
                  <CreditCard className="h-5 w-5 text-ink-secondary" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-xs font-medium text-ink-secondary">
                    Current plan
                  </p>
                  <p className="text-lg font-semibold capitalize text-ink">
                    {status.subscription_tier}
                  </p>
                </div>
              </div>
              <StatusBadge status={status.subscription_status} />
            </div>

            {status.trial_ends_at && (
              <p className="mb-3 text-xs text-ink-secondary">
                Trial ends:{" "}
                {new Date(status.trial_ends_at).toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </p>
            )}

            {status.has_payment_method && (
              <button
                type="button"
                onClick={handlePortal}
                disabled={portalLoading}
                className="inline-flex items-center gap-2 rounded-control border border-line px-4 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:bg-surface-muted"
              >
                {portalLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                Manage subscription
              </button>
            )}
          </Card>

          {/* Usage */}
          <Card className="p-6">
            <p className="mb-4 text-xs font-medium text-ink-secondary">Usage</p>
            <UsageBar used={status.monthly_tasks_used} limit={status.monthly_task_limit} />
            <p className="mt-3 text-xs text-ink-secondary">
              Resets at the start of each billing cycle
            </p>
          </Card>
        </div>
      )}

      {/* Plans grid */}
      <div>
        <h2 className="mb-4 text-[13px] font-medium text-ink-secondary">
          Available plans
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-ink-muted" aria-hidden="true" />
          </div>
        ) : plans.length === 0 ? (
          <div className="py-16 text-center text-ink-secondary">
            <CreditCard className="mx-auto mb-3 h-8 w-8 text-ink-muted" aria-hidden="true" />
            <p className="text-sm">No plans available. Configure Stripe to see pricing.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => (
              <PlanCard
                key={plan.name}
                plan={plan}
                currentTier={currentTier}
                onUpgrade={handleUpgrade}
                loading={upgradeLoading}
              />
            ))}
          </div>
        )}
      </div>

      {/* Test mode notice */}
      <div className="flex items-start gap-3 rounded-control border border-warning/20 bg-warning-soft p-4">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-ink">Stripe test mode</p>
          <p className="mt-0.5 text-xs text-ink-secondary">
            Payments are in test mode. Use card{" "}
            <code className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[11px]">
              4242 4242 4242 4242
            </code>{" "}
            with any future expiry and CVC.
          </p>
        </div>
      </div>
    </div>
  );
}
