"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "@/lib/use-api";
import { clsx } from "clsx";
import StateSourcesSection, {
  type SourceType,
  type StateSource,
} from "./_components/state-sources";
import ConnectionDetail, {
  type AppDetailField,
} from "./_components/connection-detail";
import {
  BookOpen,
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
  ChevronRight,
  ExternalLink,
  Pencil,
  Check,
  X,
  Target,
  Loader2,
  Plug,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Button,
  Badge,
  Textarea,
} from "@/app/_components/ui";

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
  /** Detail rows for the drawer — server-built, connected apps only. */
  details: AppDetailField[];
  /** Absent when the app can't be disconnected from the UI. */
  disconnect_url: string | null;
  /** HTTP verb for disconnect_url — the server owns this, not the client. */
  disconnect_method: string | null;
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

const GOAL_LABELS: Record<string, string> = {
  grow_revenue: "Grow revenue",
  acquire_users: "Acquire users",
  launch_product: "Launch product",
  raise_funding: "Raise funding",
  build_team: "Build team",
  automate_ops: "Automate operations",
  improve_retention: "Improve retention",
  expand_market: "Expand to new markets",
};

const iconMap: Record<string, React.ElementType> = {
  calendar: Calendar,
  "message-square": MessageSquare,
  "file-text": FileText,
  "book-open": BookOpen,
  code: Code,
  "credit-card": CreditCard,
  "layout-list": LayoutList,
  mail: Mail,
  "bar-chart-2": BarChart2,
  "share-2": Share2,
  users: Users,
};

// Notion and Obsidian connect through the State Engine source flow
// (/api/state/sources), not the integrations table, so the backend app catalog
// deliberately excludes them. Their cards are derived client-side from the
// state sources list so each has exactly one status.
const STATE_APPS: Pick<
  AppStatus,
  "key" | "display_name" | "description" | "category" | "icon"
>[] = [
  {
    key: "notion",
    display_name: "Notion",
    description:
      "Two-way sync between your Notion workspace and the living company state",
    category: "Company state",
    icon: "file-text",
  },
  {
    key: "obsidian",
    display_name: "Obsidian",
    description:
      "Two-way sync between your Obsidian vault and the living company state",
    category: "Company state",
    icon: "book-open",
  },
];

const statusConfig: Record<
  string,
  { label: string; color: string; Icon: React.ElementType }
> = {
  connected: {
    label: "Connected",
    color: "text-success",
    Icon: CheckCircle2,
  },
  disconnected: {
    label: "Not connected",
    color: "text-ink-secondary",
    Icon: Plug,
  },
  error: {
    label: "Error",
    color: "text-danger",
    Icon: AlertCircle,
  },
  coming_soon: {
    label: "Coming soon",
    color: "text-ink-secondary",
    Icon: Clock,
  },
};

/* ── Primary goal card ─────────────────────────────── */

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

  const goalLabel = goalType ? GOAL_LABELS[goalType] : null;

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent">
            <Target className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <h2 className="font-serif text-base font-semibold text-ink">
              Primary goal
            </h2>
            <p className="text-xs text-ink-secondary">
              Your company&apos;s north star — every agent aligns to this
            </p>
          </div>
        </div>
        {!editing && (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
            Edit
          </Button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          {/* Goal type selector */}
          <div>
            <label className="mb-2 block text-xs font-medium text-ink-secondary">
              Goal type
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(GOAL_LABELS).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setGoalType(key)}
                  className={clsx(
                    "rounded-control border px-3 py-2 text-left text-xs font-medium transition-colors duration-150",
                    goalType === key
                      ? "border-accent bg-accent-soft/50 text-ink"
                      : "border-line text-ink-secondary hover:border-ink-muted hover:text-ink"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Goal description */}
          <div>
            <label
              htmlFor="goal-description"
              className="mb-2 block text-xs font-medium text-ink-secondary"
            >
              Describe your goal in detail
            </label>
            <Textarea
              id="goal-description"
              value={goalDesc}
              onChange={(e) => setGoalDesc(e.target.value)}
              rows={4}
              placeholder="e.g. We're focused on growing monthly recurring revenue from $5K to $50K by Q4 2026. Our main strategy is converting free trial users to paid plans through better onboarding and feature discovery."
            />
            <p className="mt-1.5 text-[11px] text-ink-secondary">
              Be specific — this context helps all agents understand your
              business priorities and make better decisions.
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!goalType}
              loading={saving}
            >
              {!saving && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              Save goal
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCancel}>
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div>
          {goalLabel ? (
            <div className="space-y-3">
              <span className="font-serif text-lg font-semibold text-ink">
                {goalLabel}
              </span>
              {profile?.primary_goal_description ? (
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-secondary">
                  {profile.primary_goal_description}
                </p>
              ) : (
                <p className="text-sm italic text-ink-secondary">
                  No description yet — click edit to add details about your goal
                  so agents can better help you.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm italic text-ink-secondary">
              No primary goal set — click edit to define your company&apos;s
              north star.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

/* ── Business info card ────────────────────────────── */

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
    <Card className="p-6">
      <h2 className="mb-4 font-serif text-base font-semibold text-ink">
        Business profile
      </h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        {info.map(({ label, value }) => (
          <div key={label}>
            <p className="text-[11px] font-medium text-ink-secondary">{label}</p>
            <p className="mt-0.5 text-sm font-medium text-ink">{value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ── App card ──────────────────────────────────────── */

function AppCard({
  app,
  onConnect,
  connecting,
  onOpenDetail,
}: {
  app: AppStatus;
  onConnect?: (app: AppStatus) => void;
  connecting?: boolean;
  onOpenDetail?: (app: AppStatus) => void;
}) {
  const Icon = iconMap[app.icon] || Plug;
  const status = statusConfig[app.status] || statusConfig.coming_soon!;
  const StatusIcon = status!.Icon;
  const openable = Boolean(onOpenDetail);

  return (
    <div
      // A connected card is a button so the whole surface is one keyboard- and
      // screen-reader-addressable control; unconnected cards stay plain divs
      // because their only action is the Connect button inside them.
      {...(openable
        ? {
            role: "button" as const,
            tabIndex: 0,
            "aria-label": `View ${app.display_name} connection details`,
            onClick: () => onOpenDetail?.(app),
            onKeyDown: (e: React.KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpenDetail?.(app);
              }
            },
          }
        : {})}
      className={clsx(
        "rounded-card border bg-surface p-5 transition-colors duration-150",
        app.status === "connected" ? "border-success/30" : "border-line",
        app.status === "coming_soon" && "opacity-60",
        openable &&
          "cursor-pointer hover:border-success/60 hover:bg-surface-muted/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      )}
    >
      <div className="mb-3 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              "flex h-10 w-10 items-center justify-center rounded-lg",
              app.status === "connected" ? "bg-success-soft" : "bg-surface-muted"
            )}
          >
            <Icon
              className={clsx(
                "h-5 w-5",
                app.status === "connected" ? "text-success" : "text-ink-muted"
              )}
              aria-hidden="true"
            />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">{app.display_name}</h3>
            <span
              className={clsx(
                "inline-flex items-center gap-1 text-[11px] font-medium",
                status.color
              )}
            >
              <StatusIcon className="h-3 w-3" aria-hidden="true" />
              {status.label}
            </span>
          </div>
        </div>
      </div>

      <p className="mb-4 text-xs leading-relaxed text-ink-secondary">
        {app.description}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium capitalize text-ink-secondary">
          {app.category}
        </span>
        {app.status === "connected" ? (
          <span className="flex items-center gap-1.5 text-[11px] text-ink-secondary">
            {app.last_sync_at
              ? `Synced ${new Date(app.last_sync_at).toLocaleDateString()}`
              : "Active"}
            {openable && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-medium text-accent-text">Details</span>
                <ChevronRight className="h-3 w-3" aria-hidden="true" />
              </>
            )}
          </span>
        ) : app.connect_url && app.status !== "coming_soon" ? (
          <button
            type="button"
            onClick={() => onConnect?.(app)}
            disabled={connecting}
            className="flex items-center gap-1 rounded-control bg-accent px-3 py-1.5 text-[11px] font-medium text-white transition-colors duration-150 hover:bg-accent-hover disabled:opacity-60"
          >
            {connecting ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                Connecting
              </>
            ) : (
              <>
                Connect
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </>
            )}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/* ── Main page ─────────────────────────────────────── */

export default function AppsPage() {
  const api = useApi();
  const [apps, setApps] = useState<AppStatus[]>([]);
  const [profile, setProfile] = useState<FounderProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectingAppKey, setConnectingAppKey] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [stateSources, setStateSources] = useState<StateSource[]>([]);
  const [addingSource, setAddingSource] = useState<SourceType | null>(null);
  const [detailKey, setDetailKey] = useState<string | null>(null);
  // Bumped after a disconnect so StateSourcesSection refetches its own list.
  const [sourcesRefreshKey, setSourcesRefreshKey] = useState(0);

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

  // Route Notion/Obsidian to the state-source add form; everything else to OAuth.
  const handleConnect = useCallback(
    (app: AppStatus) => {
      if (app.key === "notion" || app.key === "obsidian") {
        setAddingSource(app.key);
        document
          .getElementById("company-state-sources")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      void handleConnectApp(app);
    },
    [handleConnectApp]
  );

  // A Notion/Obsidian type counts as connected once at least one source of that
  // type exists — per-source error/sync detail is managed in the Company State
  // Sources section above, so the card here stays a simple connected/not toggle.
  const stateApps: AppStatus[] = STATE_APPS.map((def) => {
    const sources = stateSources.filter((s) => s.type === def.key);
    const connected = sources.length > 0;
    const lastSync =
      sources
        .map((s) => s.last_synced_at)
        .filter((t): t is string => t !== null)
        .sort()
        .pop() ?? null;
    return {
      ...def,
      status: connected ? "connected" : "disconnected",
      is_active: connected,
      last_sync_at: lastSync,
      sync_status: null,
      connect_url: "/api/state/sources",
      // Detail rows come from the sources themselves, rendered by the drawer's
      // SourceList; disconnect is per-source, so there is no app-level URL.
      details: [],
      disconnect_url: null,
      disconnect_method: null,
    } satisfies AppStatus;
  });

  // Disconnect an app whose credentials the backend owns (Google Calendar via
  // the planner route, integrations-table apps via the settings route). The
  // server decides which URL applies — the client just calls what it was given.
  const handleDisconnectApp = useCallback(
    async (app: {
      key: string;
      disconnect_url: string | null;
      disconnect_method: string | null;
    }) => {
      if (!app.disconnect_url) return;
      // The URL and verb come from the API response, and api() attaches the
      // Clerk bearer token — so an absolute URL here would ship the session
      // token off-origin. Only same-origin /api/ paths and known verbs pass.
      const method = app.disconnect_method ?? "DELETE";
      if (
        !/^\/api\/[A-Za-z0-9/_-]*$/.test(app.disconnect_url) ||
        !["DELETE", "POST"].includes(method)
      ) {
        setConnectError(
          `Refusing to disconnect ${app.key}: the server returned an unexpected endpoint.`
        );
        return;
      }
      await api(app.disconnect_url, { method });
      await loadData();
    },
    [api, loadData]
  );

  const handleDisconnectSource = useCallback(
    async (source: StateSource) => {
      await api(`/api/state/sources/${source.id}`, { method: "DELETE" });
      setStateSources((prev) => prev.filter((s) => s.id !== source.id));
      setSourcesRefreshKey((k) => k + 1);
    },
    [api]
  );

  const allApps = [...stateApps, ...apps];
  // Resolved from the live list rather than stored, so the drawer re-renders
  // with fresh data after a sync or a disconnect instead of showing a snapshot.
  // Requiring "connected" also closes the drawer on its own once the last
  // source behind a card is removed — otherwise it would sit there empty.
  const detailApp =
    allApps.find((a) => a.key === detailKey && a.status === "connected") ??
    null;
  const connectedApps = allApps.filter((a) => a.status === "connected");
  const connectableApps = allApps.filter(
    (a) => a.status === "disconnected" || a.status === "error"
  );
  const comingSoonApps = allApps.filter((a) => a.status === "coming_soon");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
          <p className="text-xs text-ink-secondary">Loading</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl space-y-8">
      <PageHeader
        title="Apps"
        description="Manage your connected tools and company direction"
      />

      {connectError && (
        <div className="rounded-control border border-danger/20 bg-danger-soft px-4 py-3 text-sm text-danger">
          {connectError}
        </div>
      )}

      {/* Primary goal */}
      <PrimaryGoalCard profile={profile} onUpdate={handleUpdateProfile} />

      {/* Business info */}
      <BusinessInfoCard profile={profile} />

      {/* Company state sources (Notion / Obsidian sync management).
          Remounted on sourcesRefreshKey so a disconnect made in the detail
          drawer is reflected here without a full page reload. */}
      <StateSourcesSection
        key={sourcesRefreshKey}
        adding={addingSource}
        onAddingChange={setAddingSource}
        onSourcesChange={setStateSources}
      />

      {/* Connected */}
      {connectedApps.length > 0 && (
        <div>
          <div className="mb-4 flex items-center gap-2">
            <h2 className="font-serif text-base font-semibold text-ink">Connected</h2>
            <Badge tone="success">{connectedApps.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {connectedApps.map((app) => (
              <AppCard
                key={app.key}
                app={app}
                onOpenDetail={() => setDetailKey(app.key)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Can be connected */}
      {connectableApps.length > 0 && (
        <div>
          <div className="mb-4 flex items-center gap-2">
            <h2 className="font-serif text-base font-semibold text-ink">
              Can be connected
            </h2>
            <Badge>{connectableApps.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {connectableApps.map((app) => (
              <AppCard
                key={app.key}
                app={app}
                onConnect={handleConnect}
                connecting={connectingAppKey === app.key}
              />
            ))}
          </div>
        </div>
      )}

      {/* Coming soon */}
      {comingSoonApps.length > 0 && (
        <div>
          <div className="mb-4 flex items-center gap-2">
            <h2 className="font-serif text-base font-semibold text-ink">
              Coming soon
            </h2>
            <Badge>{comingSoonApps.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {comingSoonApps.map((app) => (
              <AppCard key={app.key} app={app} />
            ))}
          </div>
        </div>
      )}

      {/* Connection detail drawer */}
      <ConnectionDetail
        app={detailApp}
        sources={
          detailApp ? stateSources.filter((s) => s.type === detailApp.key) : []
        }
        onClose={() => setDetailKey(null)}
        onDisconnectApp={handleDisconnectApp}
        onDisconnectSource={handleDisconnectSource}
        onReconnect={(app) => {
          setDetailKey(null);
          const full = allApps.find((a) => a.key === app.key);
          if (full) void handleConnectApp(full);
        }}
        onManageSources={() => {
          setDetailKey(null);
          document
            .getElementById("company-state-sources")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />
    </div>
  );
}
