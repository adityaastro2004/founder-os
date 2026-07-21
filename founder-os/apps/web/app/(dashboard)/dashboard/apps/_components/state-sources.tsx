"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/use-api";
import { clsx } from "clsx";
import {
  AlertCircle,
  BookOpen,
  Check,
  Database,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";

/* ── Types (mirror app/api/state_routes.py response models) ── */

interface SourceHealth {
  ok: boolean;
  detail: string;
}

export interface StateSource {
  id: string;
  type: "obsidian" | "notion";
  name: string;
  config: Record<string, unknown>;
  status: "active" | "paused" | "syncing" | "error";
  last_synced_at: string | null;
  last_error: string | null;
  last_sync_report: Record<string, unknown> | null;
  health: SourceHealth | null;
}

export type SourceType = "notion" | "obsidian";

/* ── Helpers ── */

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Accepts a raw 32-hex id, a dashed UUID, or a full Notion page URL. */
function extractNotionPageId(input: string): string | null {
  const cleaned = input.trim().replace(/-/g, "").toLowerCase();
  const match = cleaned.match(/[0-9a-f]{32}/);
  return match ? match[0] : null;
}

function reportSummary(report: Record<string, unknown>): string {
  const parts: string[] = [];
  const num = (k: string) =>
    typeof report[k] === "number" ? (report[k] as number) : 0;
  if (num("observed")) parts.push(`${num("observed")} observed`);
  if (num("created")) parts.push(`${num("created")} created`);
  if (num("updated")) parts.push(`${num("updated")} updated`);
  if (num("archived")) parts.push(`${num("archived")} archived`);
  if (num("rendered_files")) parts.push(`${num("rendered_files")} files rendered`);
  if (num("pushed")) parts.push(`${num("pushed")} pushed`);
  if (num("errors")) parts.push(`${num("errors")} errors`);
  if (typeof report["duration_s"] === "number")
    parts.push(`${report["duration_s"]}s`);
  return parts.join(" · ");
}

const inputClass =
  "w-full px-3 py-2 text-sm rounded-control border border-line bg-surface placeholder:text-ink-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-all";

const labelClass =
  "block text-xs font-medium text-ink-secondary mb-1.5";

const helpClass = "text-[11px] text-ink-secondary mt-1.5";

/* ── Add-source form ── */

function AddSourceForm({
  type,
  onCancel,
  onCreated,
  api,
}: {
  type: SourceType;
  onCancel: () => void;
  onCreated: () => Promise<void>;
  api: ReturnType<typeof useApi>;
}) {
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [rootPage, setRootPage] = useState("");
  const [vaultPath, setVaultPath] = useState("");
  const [managedFolder, setManagedFolder] = useState("FounderOS");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    let config: Record<string, unknown>;
    if (type === "notion") {
      const pageId = extractNotionPageId(rootPage);
      if (!pageId) {
        setError(
          "Root page must be a Notion page URL or its 32-character ID — check the page's Copy link."
        );
        return;
      }
      if (!token.trim()) {
        setError("Integration token is required.");
        return;
      }
      config = { managed_root_page_id: pageId, token: token.trim() };
    } else {
      if (!vaultPath.trim()) {
        setError("Vault path is required.");
        return;
      }
      config = {
        vault_path: vaultPath.trim(),
        managed_folder: managedFolder.trim() || "FounderOS",
      };
    }

    setSubmitting(true);
    try {
      await api("/api/state/sources", {
        method: "POST",
        body: JSON.stringify({
          type,
          name: name.trim() || undefined,
          config,
        }),
      });
      await onCreated();
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Couldn't register the source. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-control border border-line bg-surface-muted/40 p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-sm font-semibold text-ink">
          {type === "notion" ? "Connect Notion" : "Connect Obsidian"}
        </h3>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close form"
          className="p-2 -m-1 rounded-control text-ink-secondary hover:text-ink hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-control border border-danger/20 bg-danger-soft px-3 py-2.5 text-xs text-danger"
        >
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <div>
        <label htmlFor="source-name" className={labelClass}>
          Name (optional)
        </label>
        <input
          id="source-name"
          ref={firstFieldRef}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={type === "notion" ? "Company workspace" : "My vault"}
          maxLength={255}
          autoComplete="off"
          spellCheck={false}
          className={inputClass}
        />
      </div>

      {type === "notion" ? (
        <>
          <div>
            <label htmlFor="notion-token" className={labelClass}>
              Integration token *
            </label>
            <div className="relative">
              <input
                id="notion-token"
                type={showToken ? "text" : "password"}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ntn_..."
                autoComplete="off"
                spellCheck={false}
                required
                className={clsx(inputClass, "pr-10")}
              />
              <button
                type="button"
                onClick={() => setShowToken((s) => !s)}
                aria-label={showToken ? "Hide token" : "Show token"}
                className="absolute right-1 top-1/2 -translate-y-1/2 p-2 rounded-md text-ink-secondary hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {showToken ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>
            <p className={helpClass}>
              Create an internal integration at notion.so/my-integrations with
              read, update &amp; insert capabilities. The token is stored
              server-side and never displayed again.
            </p>
          </div>
          <div>
            <label htmlFor="notion-root" className={labelClass}>
              Managed root page *
            </label>
            <input
              id="notion-root"
              type="text"
              value={rootPage}
              onChange={(e) => setRootPage(e.target.value)}
              placeholder="https://notion.so/Founder-OS-1234... or the 32-char page ID"
              autoComplete="off"
              spellCheck={false}
              required
              aria-invalid={error?.startsWith("Root page") || undefined}
              className={inputClass}
            />
            <p className={helpClass}>
              Share this page with your integration first — Founder OS builds
              its managed tree (Goals, Projects, Tasks…) under it and never
              writes outside it.
            </p>
          </div>
        </>
      ) : (
        <>
          <div>
            <label htmlFor="vault-path" className={labelClass}>
              Vault path *
            </label>
            <input
              id="vault-path"
              type="text"
              value={vaultPath}
              onChange={(e) => setVaultPath(e.target.value)}
              placeholder="/Users/you/Documents/MyVault"
              autoComplete="off"
              spellCheck={false}
              required
              className={inputClass}
            />
            <p className={helpClass}>
              Absolute path to the vault on the machine running the Founder OS
              API — Obsidian sync is local-first and reads the filesystem
              directly.
            </p>
          </div>
          <div>
            <label htmlFor="managed-folder" className={labelClass}>
              Managed folder
            </label>
            <input
              id="managed-folder"
              type="text"
              value={managedFolder}
              onChange={(e) => setManagedFolder(e.target.value)}
              pattern="[A-Za-z0-9 _\-]+"
              maxLength={255}
              autoComplete="off"
              spellCheck={false}
              className={inputClass}
            />
            <p className={helpClass}>
              Founder OS only ever writes inside this folder of your vault.
            </p>
          </div>
        </>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium bg-accent text-white rounded-control hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50 transition-colors"
        >
          {submitting ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Validating…
            </>
          ) : (
            <>
              <Check className="w-3.5 h-3.5" />
              Connect
            </>
          )}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-xs font-medium text-ink-secondary rounded-control hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors"
        >
          Cancel
        </button>
        {type === "notion" && submitting && (
          <span className="text-[11px] text-ink-secondary">
            Checking the token against your root page…
          </span>
        )}
      </div>
    </form>
  );
}

/* ── Source row ── */

const statusChip: Record<
  StateSource["status"],
  { label: string; className: string }
> = {
  active: { label: "Active", className: "bg-success-soft text-success" },
  paused: {
    label: "Paused",
    className: "bg-surface-muted text-ink-secondary",
  },
  syncing: { label: "Syncing", className: "bg-accent-soft text-accent-text" },
  error: { label: "Error", className: "bg-danger-soft text-danger" },
};

function SourceRow({
  source,
  busy,
  onSync,
  onTogglePause,
  onDelete,
}: {
  source: StateSource;
  busy: string | null;
  onSync: () => void;
  onTogglePause: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const Icon = source.type === "notion" ? FileText : BookOpen;
  const chip = statusChip[source.status] ?? statusChip.active;
  const syncing = source.status === "syncing" || busy === "sync";
  const configHint =
    source.type === "notion"
      ? `page ${String(source.config.managed_root_page_id ?? "").slice(0, 8)}…`
      : String(source.config.vault_path ?? "");

  useEffect(() => {
    if (!confirmDelete) return;
    const timer = setTimeout(() => setConfirmDelete(false), 4000);
    return () => clearTimeout(timer);
  }, [confirmDelete]);

  const iconButton =
    "p-2 rounded-control text-ink-secondary hover:text-ink hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40 transition-colors";

  return (
    <li className="flex flex-col gap-2 rounded-card border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-surface-muted">
          <Icon className="h-4.5 w-4.5 text-ink-secondary" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{source.name}</span>
            <span className="text-[10px] uppercase tracking-wider font-medium text-ink-secondary">
              {source.type}
            </span>
            <span
              className={clsx(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                chip.className
              )}
            >
              {syncing && <Loader2 className="h-3 w-3 animate-spin" />}
              {syncing ? "Syncing" : chip.label}
            </span>
            {source.health && !source.health.ok && (
              <span
                className="inline-flex items-center gap-1 text-[11px] font-medium text-warning"
                title={source.health.detail}
              >
                <AlertCircle className="h-3 w-3" />
                Needs attention
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-ink-secondary">
            {configHint}
            {source.last_synced_at &&
              ` · synced ${timeAgo(source.last_synced_at)}`}
          </p>
          {source.status === "error" && source.last_error && (
            <p className="mt-1 text-xs text-danger line-clamp-2">
              {source.last_error}
            </p>
          )}
          {source.health && !source.health.ok && (
            <p className="mt-1 text-xs text-warning line-clamp-2">
              {source.health.detail}
            </p>
          )}
          {source.last_sync_report &&
            reportSummary(source.last_sync_report) && (
              <p className="mt-1 text-[11px] text-ink-secondary">
                Last sync: {reportSummary(source.last_sync_report)}
              </p>
            )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1 self-end sm:self-center">
        <button
          type="button"
          onClick={onSync}
          disabled={syncing || source.status === "paused" || busy !== null}
          aria-label={`Sync ${source.name} now`}
          title={source.status === "paused" ? "Resume to sync" : "Sync now"}
          className={iconButton}
        >
          <RefreshCw className={clsx("h-4 w-4", syncing && "animate-spin")} />
        </button>
        <button
          type="button"
          onClick={onTogglePause}
          disabled={syncing || busy !== null}
          aria-label={
            source.status === "paused"
              ? `Resume ${source.name}`
              : `Pause ${source.name}`
          }
          title={source.status === "paused" ? "Resume" : "Pause"}
          className={iconButton}
        >
          {busy === "pause" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : source.status === "paused" ? (
            <Play className="h-4 w-4" />
          ) : (
            <Pause className="h-4 w-4" />
          )}
        </button>
        {confirmDelete ? (
          <button
            type="button"
            onClick={onDelete}
            disabled={busy !== null}
            aria-label={`Confirm removing ${source.name}`}
            className="flex items-center gap-1 rounded-control bg-danger px-3 py-2 text-[11px] font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50 transition-colors"
          >
            {busy === "delete" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            Remove?
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={busy !== null}
            aria-label={`Remove ${source.name}`}
            title="Remove source"
            className={clsx(iconButton, "hover:text-danger")}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </li>
  );
}

/* ── Section ── */

const POLL_INTERVAL_MS = 5000;
const POLL_MAX = 18; // ~90s; first Notion walk can take longer — stop politely

export default function StateSourcesSection({
  adding,
  onAddingChange,
  onSourcesChange,
}: {
  /** Which add-source form is open — controlled by the apps page, so the
   *  "Connect" buttons on the Notion/Obsidian app cards can open it. */
  adding: SourceType | null;
  onAddingChange: (type: SourceType | null) => void;
  /** Reports the loaded sources up so the apps page can group the Notion /
   *  Obsidian cards under Connected vs. Can be connected. */
  onSourcesChange?: (sources: StateSource[]) => void;
}) {
  const api = useApi();
  const [sources, setSources] = useState<StateSource[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const pollTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const data = await api("/api/state/sources");
      setSources(data.sources ?? []);
      onSourcesChange?.(data.sources ?? []);
    } catch (err) {
      setLoadError(
        err instanceof Error && err.message
          ? err.message
          : "Couldn't load sources."
      );
      setSources((prev) => prev ?? []);
    }
  }, [api, onSourcesChange]);

  useEffect(() => {
    load();
    const timers = pollTimers.current;
    return () => Object.values(timers).forEach(clearTimeout);
  }, [load]);

  const setSourceBusy = (id: string, action: string | null) =>
    setBusy((prev) => {
      const next = { ...prev };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });

  /** Poll one source until it leaves "syncing", then refresh the whole list
   *  (cheap GET; capped at POLL_MAX so a long first walk doesn't poll forever). */
  const pollSource = useCallback(
    (id: string, attempt = 0) => {
      if (attempt >= POLL_MAX) {
        setNotice(
          "Sync is still running in the background — refresh in a few minutes to see the result."
        );
        setSourceBusy(id, null);
        void load();
        return;
      }
      pollTimers.current[id] = setTimeout(async () => {
        try {
          const s: StateSource = await api(`/api/state/sources/${id}`);
          if (s.status === "syncing") {
            setSources((prev) =>
              prev?.map((x) => (x.id === id ? { ...x, status: s.status } : x)) ??
              prev
            );
            pollSource(id, attempt + 1);
            return;
          }
          setSourceBusy(id, null);
          await load();
        } catch {
          setSourceBusy(id, null);
          void load();
        }
      }, POLL_INTERVAL_MS);
    },
    [api, load]
  );

  const handleSync = async (source: StateSource) => {
    setNotice(null);
    setSourceBusy(source.id, "sync");
    try {
      await api(`/api/state/sources/${source.id}/sync`, {
        method: "POST",
        body: JSON.stringify({ direction: "both" }),
      });
      setSources(
        (prev) =>
          prev?.map((x) =>
            x.id === source.id ? { ...x, status: "syncing" as const } : x
          ) ?? prev
      );
      pollSource(source.id);
    } catch (err) {
      setSourceBusy(source.id, null);
      const msg = err instanceof Error ? err.message : "";
      if (msg.toLowerCase().includes("already running")) {
        setSources(
          (prev) =>
            prev?.map((x) =>
              x.id === source.id ? { ...x, status: "syncing" as const } : x
            ) ?? prev
        );
        pollSource(source.id);
      } else {
        setNotice(msg || "Couldn't start the sync. Please try again.");
      }
    }
  };

  const handleTogglePause = async (source: StateSource) => {
    setNotice(null);
    setSourceBusy(source.id, "pause");
    try {
      await api(`/api/state/sources/${source.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: source.status === "paused" ? "active" : "paused",
        }),
      });
      await load();
    } catch (err) {
      setNotice(
        err instanceof Error && err.message
          ? err.message
          : "Couldn't update the source."
      );
    } finally {
      setSourceBusy(source.id, null);
    }
  };

  const handleDelete = async (source: StateSource) => {
    setNotice(null);
    setSourceBusy(source.id, "delete");
    try {
      await api(`/api/state/sources/${source.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setNotice(
        err instanceof Error && err.message
          ? err.message
          : "Couldn't remove the source."
      );
    } finally {
      setSourceBusy(source.id, null);
    }
  };

  return (
    <div
      id="company-state-sources"
      className="scroll-mt-6 rounded-card border border-line bg-surface p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-control bg-accent flex items-center justify-center">
            <Database className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="font-serif text-base font-semibold text-ink">
              Company state sources
            </h2>
            <p className="text-xs text-ink-secondary">
              Sync Notion or Obsidian into your living company model — both
              ways
            </p>
          </div>
        </div>
      </div>

      {notice && (
        <div
          role="status"
          className="mb-4 flex items-start justify-between gap-2 rounded-control border border-line bg-surface-muted/40 px-3 py-2.5 text-xs text-ink-secondary"
        >
          <span>{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label="Dismiss"
            className="p-1 -m-1 rounded text-ink-secondary hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {adding !== null && (
        <div className="mb-4">
          <AddSourceForm
            type={adding}
            api={api}
            onCancel={() => onAddingChange(null)}
            onCreated={async () => {
              onAddingChange(null);
              await load();
            }}
          />
        </div>
      )}

      {sources === null ? (
        <ul className="space-y-3" aria-hidden="true">
          {[0, 1].map((i) => (
            <li
              key={i}
              className="h-16 animate-pulse rounded-control bg-surface-muted"
            />
          ))}
        </ul>
      ) : loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-control border border-danger/20 bg-danger-soft px-4 py-3">
          <p className="text-sm text-danger">{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setSources(null);
              void load();
            }}
            className="shrink-0 rounded-control px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-danger transition-colors"
          >
            Retry
          </button>
        </div>
      ) : sources.length === 0 ? (
        adding === null && (
          <div className="rounded-control border border-dashed border-line px-6 py-8 text-center">
            <Database className="mx-auto h-6 w-6 text-ink-secondary" />
            <p className="mt-2 text-sm font-medium">No sources connected yet</p>
            <p className="mx-auto mt-1 max-w-md text-xs text-ink-secondary">
              Connect Notion or Obsidian from &ldquo;Can be connected&rdquo;
              below and Founder OS keeps a unified, living model of your
              company in sync — goals, projects, tasks, and decisions with
              full provenance.
            </p>
          </div>
        )
      ) : (
        <ul className="space-y-3">
          {sources.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              busy={busy[source.id] ?? null}
              onSync={() => handleSync(source)}
              onTogglePause={() => handleTogglePause(source)}
              onDelete={() => handleDelete(source)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
