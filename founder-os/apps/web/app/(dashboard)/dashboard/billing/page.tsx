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
    gradient: string;
    badge: string;
    popular?: boolean;
  }
> = {
  free: {
    icon: Zap,
    gradient: "from-gray-50 to-gray-100",
    badge: "bg-gray-100 text-gray-600",
  },
  starter: {
    icon: Sparkles,
    gradient: "from-blue-50 to-indigo-50",
    badge: "bg-blue-50 text-blue-700",
    popular: true,
  },
  pro: {
    icon: Crown,
    gradient: "from-violet-50 to-purple-50",
    badge: "bg-violet-50 text-violet-700",
  },
  enterprise: {
    icon: Building2,
    gradient: "from-amber-50 to-orange-50",
    badge: "bg-amber-50 text-amber-700",
  },
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

/* ── Status Badge ─────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; label: string }> = {
    active: { color: "text-emerald-700 bg-emerald-50 border-emerald-200", label: "Active" },
    trial: { color: "text-blue-700 bg-blue-50 border-blue-200", label: "Trial" },
    past_due: { color: "text-amber-700 bg-amber-50 border-amber-200", label: "Past Due" },
    canceled: { color: "text-red-700 bg-red-50 border-red-200", label: "Canceled" },
  };
  const c = config[status] ?? config.trial!;
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border",
        c.color
      )}
    >
      {c.label}
    </span>
  );
}

/* ── Usage Bar ────────────────────────────────────── */
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
        <span className="text-[var(--color-text-secondary)]">Tasks this month</span>
        <span className={clsx("font-medium tabular-nums", isFull && "text-[var(--color-danger)]")}>
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
        <div
          className={clsx(
            "h-full rounded-full transition-all duration-500 ease-out",
            isFull
              ? "bg-[var(--color-danger)]"
              : isHigh
                ? "bg-[var(--color-warning)]"
                : "bg-[var(--color-accent)]"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ── Plan Card ────────────────────────────────────── */
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
        "relative rounded-xl border p-6 flex flex-col transition-all duration-200",
        isCurrent
          ? "border-[var(--color-accent)] bg-[var(--color-surface)] ring-1 ring-[var(--color-accent)]/10"
          : "border-[var(--color-border-subtle)] bg-[var(--color-surface)] hover:border-[var(--color-border)] hover:shadow-sm"
      )}
    >
      {/* Popular badge */}
      {config.popular && !isCurrent && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="px-3 py-1 bg-[var(--color-accent)] text-[var(--color-accent-foreground)] text-[10px] font-semibold uppercase tracking-wider rounded-full">
            Most Popular
          </span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <div
          className={clsx(
            "w-9 h-9 rounded-lg flex items-center justify-center bg-gradient-to-br",
            config.gradient
          )}
        >
          <Icon className="w-4.5 h-4.5 text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">{plan.display_name || plan.name}</h3>
          {isCurrent && (
            <span className="text-[10px] font-medium text-[var(--color-accent)] uppercase tracking-wider">
              Current Plan
            </span>
          )}
        </div>
      </div>

      {/* Price */}
      <div className="mb-4">
        {isFreePlan ? (
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold tracking-tight">$0</span>
            <span className="text-sm text-[var(--color-text-muted)]">forever</span>
          </div>
        ) : (
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-bold tracking-tight">
              ${plan.price_monthly_usd}
            </span>
            <span className="text-sm text-[var(--color-text-muted)]">/mo</span>
          </div>
        )}
        {plan.price_yearly_usd && !isFreePlan && (
          <p className="text-xs text-[var(--color-text-muted)] mt-1">
            ${plan.price_yearly_usd}/yr (save{" "}
            {Math.round(
              100 - (plan.price_yearly_usd / ((plan.price_monthly_usd || 1) * 12)) * 100
            )}
            %)
          </p>
        )}
      </div>

      {/* Description */}
      <p className="text-sm text-[var(--color-text-secondary)] mb-5 leading-relaxed">
        {plan.description || "—"}
      </p>

      {/* Limits */}
      <div className="space-y-2.5 mb-6 flex-1">
        <LimitRow label="Tasks / month" value={plan.monthly_task_limit} unlimited={(plan.monthly_task_limit ?? 0) > 99999} />
        <LimitRow label="Agents" value={plan.agent_limit} />
        <LimitRow label="Workflows" value={plan.workflow_limit} />
        <LimitRow label="Knowledge items" value={plan.knowledge_items_limit} />
        <LimitRow label="Team members" value={plan.team_members_limit} />
      </div>

      {/* Features */}
      {plan.features && plan.features.length > 0 && (
        <div className="border-t border-[var(--color-border-subtle)] pt-4 mb-5">
          <p className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2.5">
            Includes
          </p>
          <ul className="space-y-1.5">
            {plan.features.map((f: string) => (
              <li key={f} className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <Check className="w-3.5 h-3.5 text-[var(--color-success)] shrink-0" />
                {FEATURE_LABELS[f] || f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action button */}
      {isCurrent ? (
        <button
          disabled
          className="w-full py-2.5 px-4 rounded-lg text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-muted)] cursor-default"
        >
          Current Plan
        </button>
      ) : isFreePlan || isDowngrade ? (
        <button
          disabled
          className="w-full py-2.5 px-4 rounded-lg text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-muted)] cursor-default"
        >
          {isDowngrade ? "Downgrade via Portal" : "Free"}
        </button>
      ) : (
        <button
          onClick={() => onUpgrade(plan.name)}
          disabled={loading}
          className={clsx(
            "w-full py-2.5 px-4 rounded-lg text-sm font-medium transition-all duration-150 flex items-center justify-center gap-2",
            config.popular
              ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:bg-[var(--color-accent-hover)]"
              : "border border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-surface-muted)]"
          )}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <>
              Upgrade
              <ArrowRight className="w-3.5 h-3.5" />
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
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className="font-medium tabular-nums">
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
      setToast({ type: "success", message: "Subscription activated! Welcome aboard 🎉" });
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
    <div className="space-y-8 max-w-6xl">
      {/* Toast */}
      {toast && (
        <div
          className={clsx(
            "flex items-center gap-3 p-4 rounded-lg border animate-in fade-in slide-in-from-top-2 duration-300",
            toast.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          )}
        >
          {toast.type === "success" ? (
            <CheckCircle2 className="w-4.5 h-4.5 shrink-0" />
          ) : (
            <AlertCircle className="w-4.5 h-4.5 shrink-0" />
          )}
          <p className="text-sm font-medium flex-1">{toast.message}</p>
          <button
            onClick={() => setToast(null)}
            className="text-sm opacity-60 hover:opacity-100"
          >
            ×
          </button>
        </div>
      )}

      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Billing</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Manage your subscription and usage
        </p>
      </div>

      {/* Current plan + usage card */}
      {status && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Current plan */}
          <div className="bg-white rounded-xl border border-[var(--color-border-subtle)] p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
                  <CreditCard className="w-5 h-5 text-[var(--color-text-secondary)]" />
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider font-medium">
                    Current Plan
                  </p>
                  <p className="text-lg font-semibold capitalize">{status.subscription_tier}</p>
                </div>
              </div>
              <StatusBadge status={status.subscription_status} />
            </div>

            {status.trial_ends_at && (
              <p className="text-xs text-[var(--color-text-muted)] mb-3">
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
                onClick={handlePortal}
                disabled={portalLoading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                {portalLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ExternalLink className="w-3.5 h-3.5" />
                )}
                Manage Subscription
              </button>
            )}
          </div>

          {/* Usage */}
          <div className="bg-white rounded-xl border border-[var(--color-border-subtle)] p-6">
            <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider font-medium mb-4">
              Usage
            </p>
            <UsageBar used={status.monthly_tasks_used} limit={status.monthly_task_limit} />
            <p className="text-xs text-[var(--color-text-muted)] mt-3">
              Resets at the start of each billing cycle
            </p>
          </div>
        </div>
      )}

      {/* Plans grid */}
      <div>
        <h2 className="text-sm font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-4">
          Available Plans
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-muted)]" />
          </div>
        ) : plans.length === 0 ? (
          <div className="text-center py-16 text-[var(--color-text-secondary)]">
            <CreditCard className="w-8 h-8 mx-auto mb-3 text-[var(--color-text-muted)]" />
            <p className="text-sm">No plans available. Configure Stripe to see pricing.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
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
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex items-start gap-3">
        <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-amber-800">Stripe Test Mode</p>
          <p className="text-xs text-amber-700 mt-0.5">
            Payments are in test mode. Use card{" "}
            <code className="px-1.5 py-0.5 bg-amber-100 rounded text-[11px] font-mono">
              4242 4242 4242 4242
            </code>{" "}
            with any future expiry and CVC.
          </p>
        </div>
      </div>
    </div>
  );
}
