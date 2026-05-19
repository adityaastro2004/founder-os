"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import { clsx } from "clsx";
import {
  Calendar,
  MessageSquare,
  FileText,
  Code,
  CreditCard,
  LayoutList,
  Mail,
  BarChart2,
  Share2,
  Users,
  CheckCircle2,
  Clock,
  AlertCircle,
  ExternalLink,
  Pencil,
  Check,
  X,
  Target,
  Loader2,
  Plug,
} from "lucide-react";

/* ── Types ─────────────────────────────────────────── */

interface AppStatus {
  key: string;
  display_name: string;
  description: string;
  category: string;
  icon: string;
  status: "connected" | "disconnected" | "error" | "coming_soon";
  is_active: boolean;
  last_sync_at: string | null;
  sync_status: string | null;
  connect_url: string | null;
}

interface FounderProfile {
  id: string;
  business_name: string | null;
  business_type: string | null;
  business_stage: string | null;
  industry: string | null;
  target_audience: string | null;
  primary_goal: string | null;
  primary_goal_description: string | null;
  team_size: number;
  team_roles: string[] | null;
  current_mrr: number | null;
  current_users: number | null;
  monthly_traffic: number | null;
  preferred_communication: string | null;
  writing_voice: string | null;
  working_hours: Record<string, unknown> | null;
}

/* ── Constants ─────────────────────────────────────── */

const GOAL_LABELS: Record<string, { label: string; emoji: string }> = {
  grow_revenue: { label: "Grow Revenue", emoji: "💸" },
  acquire_users: { label: "Acquire Users", emoji: "👥" },
  launch_product: { label: "Launch Product", emoji: "🚀" },
  raise_funding: { label: "Raise Funding", emoji: "🤝" },
  build_team: { label: "Build Team", emoji: "🧑‍🤝‍🧑" },
  automate_ops: { label: "Automate Operations", emoji: "⚡" },
  improve_retention: { label: "Improve Retention", emoji: "🔄" },
  expand_market: { label: "Expand to New Markets", emoji: "🌍" },
};

const iconMap: Record<string, React.ElementType> = {
  calendar: Calendar,
  "message-square": MessageSquare,
  "file-text": FileText,
  code: Code,
  "credit-card": CreditCard,
  "layout-list": LayoutList,
  mail: Mail,
  "bar-chart-2": BarChart2,
  "share-2": Share2,
  users: Users,
};

const statusConfig: Record<
  string,
  { label: string; color: string; bgColor: string; Icon: React.ElementType }
> = {
  connected: {
    label: "Connected",
    color: "text-[var(--color-success)]",
    bgColor: "bg-green-50",
    Icon: CheckCircle2,
  },
  disconnected: {
    label: "Not connected",
    color: "text-[var(--color-text-muted)]",
    bgColor: "bg-[var(--color-surface-subtle)]",
    Icon: Plug,
  },
  error: {
    label: "Error",
    color: "text-red-500",
    bgColor: "bg-red-50",
    Icon: AlertCircle,
  },
  coming_soon: {
    label: "Coming soon",
    color: "text-[var(--color-text-muted)]",
    bgColor: "bg-[var(--color-surface-subtle)]",
    Icon: Clock,
  },
};

/* ── Primary Goal Card ─────────────────────────────── */

function PrimaryGoalCard({
  profile,
  onUpdate,
}: {
  profile: FounderProfile | null;
  onUpdate: (data: Partial<FounderProfile>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [goalType, setGoalType] = useState(profile?.primary_goal || "");
  const [goalDesc, setGoalDesc] = useState(
    profile?.primary_goal_description || ""
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setGoalType(profile.primary_goal || "");
      setGoalDesc(profile.primary_goal_description || "");
    }
  }, [profile]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdate({
        primary_goal: goalType,
        primary_goal_description: goalDesc,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setGoalType(profile?.primary_goal || "");
    setGoalDesc(profile?.primary_goal_description || "");
    setEditing(false);
  };

  const goalInfo = goalType ? GOAL_LABELS[goalType] : null;

  return (
    <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
            <Target className="w-5 h-5 text-[var(--color-accent-foreground)]" />
          </div>
          <div>
            <h2 className="text-base font-semibold">Primary Goal</h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Your company&apos;s north star — every agent aligns to this
            </p>
          </div>
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-muted)] rounded-lg transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          {/* Goal type selector */}
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
              Goal Type
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.entries(GOAL_LABELS).map(([key, { label, emoji }]) => (
                <button
                  key={key}
                  onClick={() => setGoalType(key)}
                  className={clsx(
                    "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-all",
                    goalType === key
                      ? "border-[var(--color-accent)] bg-[var(--color-surface-muted)] text-[var(--color-text)]"
                      : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-text-muted)]"
                  )}
                >
                  <span>{emoji}</span>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Goal description */}
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
              Describe your goal in detail
            </label>
            <textarea
              value={goalDesc}
              onChange={(e) => setGoalDesc(e.target.value)}
              rows={4}
              placeholder="e.g. We're focused on growing monthly recurring revenue from $5K to $50K by Q4 2026. Our main strategy is converting free trial users to paid plans through better onboarding and feature discovery..."
              className="w-full px-3 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-white placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-text)] resize-none transition-all"
            />
            <p className="text-[11px] text-[var(--color-text-muted)] mt-1.5">
              Be specific — this context helps all agents understand your
              business priorities and make better decisions.
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={saving || !goalType}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium bg-[var(--color-accent)] text-[var(--color-accent-foreground)] rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            >
              {saving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Check className="w-3.5 h-3.5" />
              )}
              Save Goal
            </button>
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] rounded-lg transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div>
          {goalInfo ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xl">{goalInfo.emoji}</span>
                <span className="text-lg font-semibold">{goalInfo.label}</span>
              </div>
              {profile?.primary_goal_description ? (
                <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-wrap">
                  {profile.primary_goal_description}
                </p>
              ) : (
                <p className="text-sm text-[var(--color-text-muted)] italic">
                  No description yet — click Edit to add details about your goal
                  so agents can better help you.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)] italic">
              No primary goal set — click Edit to define your company&apos;s
              north star.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Business Info Card ────────────────────────────── */

function BusinessInfoCard({ profile }: { profile: FounderProfile | null }) {
  if (!profile) return null;

  const info = [
    { label: "Company", value: profile.business_name },
    { label: "Type", value: profile.business_type },
    { label: "Industry", value: profile.industry },
    { label: "Stage", value: profile.business_stage },
    { label: "Team size", value: profile.team_size?.toString() },
    { label: "Audience", value: profile.target_audience },
  ].filter((i) => i.value);

  if (info.length === 0) return null;

  return (
    <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-6">
      <h2 className="text-base font-semibold mb-4">Business Profile</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {info.map(({ label, value }) => (
          <div key={label}>
            <p className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider font-medium">
              {label}
            </p>
            <p className="text-sm font-medium mt-0.5">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── App Card ──────────────────────────────────────── */

function AppCard({
  app,
  onConnect,
  connecting,
}: {
  app: AppStatus;
  onConnect?: (app: AppStatus) => void;
  connecting?: boolean;
}) {
  const Icon = iconMap[app.icon] || Plug;
  const status = statusConfig[app.status] || statusConfig.coming_soon!;
  const StatusIcon = status!.Icon;

  return (
    <div
      className={clsx(
        "bg-white rounded-lg border p-5 transition-all",
        app.status === "connected"
          ? "border-green-200"
          : "border-[var(--color-border-subtle)]",
        app.status === "coming_soon" ? "opacity-60" : ""
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              "w-10 h-10 rounded-lg flex items-center justify-center",
              app.status === "connected"
                ? "bg-green-50"
                : "bg-[var(--color-surface-muted)]"
            )}
          >
            <Icon
              className={clsx(
                "w-5 h-5",
                app.status === "connected"
                  ? "text-green-600"
                  : "text-[var(--color-text-muted)]"
              )}
            />
          </div>
          <div>
            <h3 className="text-sm font-semibold">{app.display_name}</h3>
            <span
              className={clsx(
                "inline-flex items-center gap-1 text-[11px] font-medium",
                status.color
              )}
            >
              <StatusIcon className="w-3 h-3" />
              {status.label}
            </span>
          </div>
        </div>
      </div>

      <p className="text-xs text-[var(--color-text-secondary)] mb-4 leading-relaxed">
        {app.description}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider font-medium">
          {app.category}
        </span>
        {app.status === "connected" ? (
          <span className="text-[11px] text-[var(--color-text-muted)]">
            {app.last_sync_at
              ? `Synced ${new Date(app.last_sync_at).toLocaleDateString()}`
              : "Active"}
          </span>
        ) : app.connect_url && app.status !== "coming_soon" ? (
          <button
            type="button"
            onClick={() => onConnect?.(app)}
            disabled={connecting}
            className="flex items-center gap-1 px-3 py-1.5 text-[11px] font-medium bg-[var(--color-accent)] text-[var(--color-accent-foreground)] rounded-md hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-60"
          >
            {connecting ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                Connecting
              </>
            ) : (
              <>
                Connect
                <ExternalLink className="w-3 h-3" />
              </>
            )}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────── */

export default function AppsPage() {
  const api = useApi();
  const [apps, setApps] = useState<AppStatus[]>([]);
  const [profile, setProfile] = useState<FounderProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectingAppKey, setConnectingAppKey] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [appsData, profileData] = await Promise.all([
        api("/api/settings/apps").catch(() => []),
        api("/api/settings/profile").catch(() => null),
      ]);
      setApps(appsData);
      setProfile(profileData);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpdateProfile = async (data: Partial<FounderProfile>) => {
    const updated = await api("/api/settings/profile", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    setProfile(updated);
  };

  const handleConnectApp = useCallback(
    async (app: AppStatus) => {
      if (!app.connect_url || app.status === "coming_soon") return;

      setConnectError(null);
      setConnectingAppKey(app.key);
      let waitingForPopupClose = false;

      const beginOauthFlow = async (data: unknown) => {
        const payload = (data ?? {}) as {
          status?: string;
          auth_url?: string;
          redirect_url?: string;
          message?: string;
        };

        if (payload.status === "already_connected") {
          await loadData();
          return true;
        }

        if (typeof payload.auth_url === "string" && payload.auth_url.length > 0) {
          const popup = window.open(
            payload.auth_url,
            `${app.key}-connect`,
            "width=600,height=700,popup=yes"
          );

          if (popup) {
            waitingForPopupClose = true;
            const timer = setInterval(() => {
              if (popup.closed) {
                clearInterval(timer);
                setConnectingAppKey(null);
                void loadData();
              }
            }, 500);
            return true;
          }

          // Popup blocked: continue in current tab
          window.location.href = payload.auth_url;
          return true;
        }

        if (
          typeof payload.redirect_url === "string" &&
          payload.redirect_url.length > 0
        ) {
          window.location.href = payload.redirect_url;
          return true;
        }

        const message =
          typeof payload.message === "string" && payload.message.length > 0
            ? payload.message
            : `Couldn't start ${app.display_name} connection. Please try again.`;
        setConnectError(message);
        return false;
      };

      try {
        const data = await api(app.connect_url);
        await beginOauthFlow(data);
      } catch (err: unknown) {
        // Retry direct-to-backend in case Next.js proxy/middleware path fails.
        try {
          const data = await api(app.connect_url, { direct: true });
          const started = await beginOauthFlow(data);
          if (started) {
            return;
          }
        } catch {
          let raw = "";
          if (typeof err === "string") {
            raw = err;
          } else if (
            err &&
            typeof err === "object" &&
            "message" in err &&
            typeof (err as { message?: unknown }).message === "string"
          ) {
            raw = (err as { message: string }).message;
          }

          if (raw.toLowerCase().includes("missing authentication token")) {
            setConnectError(
              "Authentication token missing. Refresh the page and sign in again, then retry connect."
            );
          } else {
            setConnectError(
              raw ||
              "Couldn't start connection. Your session may have expired. Refresh and try again."
            );
          }
        }
      } finally {
        if (!waitingForPopupClose) {
          setConnectingAppKey((current) =>
            current === app.key ? null : current
          );
        }
      }
    },
    [api, loadData]
  );

  const connectedApps = apps.filter((a) => a.status === "connected");
  const availableApps = apps.filter((a) => a.status !== "connected");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 text-[var(--color-text-muted)] animate-spin" />
          <p className="text-xs text-[var(--color-text-muted)]">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Apps & Goals</h1>
        <p className="text-[var(--color-text-secondary)] mt-1">
          Manage your connected tools and company direction
        </p>
      </div>

      {connectError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {connectError}
        </div>
      )}

      {/* Primary Goal */}
      <PrimaryGoalCard profile={profile} onUpdate={handleUpdateProfile} />

      {/* Business Info */}
      <BusinessInfoCard profile={profile} />

      {/* Connected Apps */}
      {connectedApps.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-base font-semibold">Connected</h2>
            <span className="px-2 py-0.5 text-[11px] font-medium bg-green-50 text-green-700 rounded-full">
              {connectedApps.length}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {connectedApps.map((app) => (
              <AppCard key={app.key} app={app} />
            ))}
          </div>
        </div>
      )}

      {/* Available Apps */}
      <div>
        <h2 className="text-base font-semibold mb-4">
          {connectedApps.length > 0 ? "Available Apps" : "Apps & Integrations"}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {availableApps.map((app) => (
            <AppCard
              key={app.key}
              app={app}
              onConnect={handleConnectApp}
              connecting={connectingAppKey === app.key}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
