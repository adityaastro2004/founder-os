"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  AlertCircle,
  ExternalLink,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Dialog, Button } from "@/app/_components/ui";
import type { StateSource } from "./state-sources";

/* ── Types ─────────────────────────────────────────── */

export interface AppDetailField {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning" | "danger";
}

export interface ConnectionApp {
  key: string;
  display_name: string;
  description: string;
  category: string;
  status: string;
  last_sync_at: string | null;
  details: AppDetailField[];
  disconnect_url: string | null;
  disconnect_method: string | null;
}

const toneClass: Record<string, string> = {
  default: "text-ink",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

/* ── Field list ────────────────────────────────────── */

function FieldList({ fields }: { fields: AppDetailField[] }) {
  if (fields.length === 0) {
    return (
      <p className="text-sm italic text-ink-secondary">
        No additional details reported for this connection.
      </p>
    );
  }

  return (
    <dl className="divide-y divide-line-subtle">
      {fields.map((field) => (
        <div
          key={field.label}
          className="flex items-baseline justify-between gap-4 py-2.5"
        >
          <dt className="shrink-0 text-xs font-medium text-ink-secondary">
            {field.label}
          </dt>
          <dd
            className={clsx(
              "text-right text-sm break-words",
              toneClass[field.tone ?? "default"],
            )}
          >
            {field.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ── State-source rows (Notion / Obsidian) ─────────── */

/** Notion and Obsidian connect as one-or-more state sources, so "disconnect"
 *  is per source. Sync and pause deliberately stay in the Company state
 *  sources section — duplicating them here would give the same action two
 *  homes and two busy states. */
function SourceList({
  sources,
  onDisconnect,
  onManage,
}: {
  sources: StateSource[];
  onDisconnect: (source: StateSource) => Promise<void>;
  onManage: () => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!confirming) return;
    const timer = setTimeout(() => setConfirming(null), 4000);
    return () => clearTimeout(timer);
  }, [confirming]);

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {sources.map((source) => (
          <li
            key={source.id}
            className="rounded-control border border-line px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">
                  {source.name}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-ink-secondary">
                  {source.type === "notion"
                    ? `page ${String(
                        source.config.managed_root_page_id ?? "",
                      ).slice(0, 8)}…`
                    : String(source.config.vault_path ?? "")}
                </p>
                {source.last_error && (
                  <p className="mt-1 flex items-start gap-1 text-[11px] text-danger">
                    <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
                    {source.last_error}
                  </p>
                )}
              </div>
              {confirming === source.id ? (
                <button
                  type="button"
                  onClick={async () => {
                    setBusyId(source.id);
                    try {
                      await onDisconnect(source);
                    } finally {
                      setBusyId(null);
                      setConfirming(null);
                    }
                  }}
                  disabled={busyId !== null}
                  className="flex shrink-0 items-center gap-1 rounded-control bg-danger px-2.5 py-1.5 text-[11px] font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
                >
                  {busyId === source.id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  Confirm
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(source.id)}
                  disabled={busyId !== null}
                  aria-label={`Disconnect ${source.name}`}
                  className="shrink-0 rounded-control px-2.5 py-1.5 text-[11px] font-medium text-ink-secondary transition-colors hover:bg-danger-soft hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
                >
                  Disconnect
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <Button variant="ghost" size="sm" onClick={onManage}>
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Sync &amp; pause options
      </Button>
    </div>
  );
}

/* ── Drawer ────────────────────────────────────────── */

export default function ConnectionDetail({
  app,
  sources,
  onClose,
  onDisconnectApp,
  onDisconnectSource,
  onReconnect,
  onManageSources,
}: {
  app: ConnectionApp | null;
  /** Only for the Notion / Obsidian cards, which are backed by state sources. */
  sources: StateSource[];
  onClose: () => void;
  onDisconnectApp: (app: ConnectionApp) => Promise<void>;
  onDisconnectSource: (source: StateSource) => Promise<void>;
  onReconnect: (app: ConnectionApp) => void;
  onManageSources: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the confirm/error state whenever a different connection is opened,
  // so a primed "Confirm disconnect" never carries over to another app.
  useEffect(() => {
    setConfirming(false);
    setBusy(false);
    setError(null);
  }, [app?.key]);

  useEffect(() => {
    if (!confirming) return;
    const timer = setTimeout(() => setConfirming(false), 4000);
    return () => clearTimeout(timer);
  }, [confirming]);

  if (!app) return null;

  const isStateApp = app.key === "notion" || app.key === "obsidian";

  const handleDisconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await onDisconnectApp(app);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Couldn't disconnect. Please try again.",
      );
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      side="right"
      onClose={onClose}
      title={app.display_name}
      footer={
        isStateApp ? undefined : app.disconnect_url ? (
          confirming ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={handleDisconnect}
                loading={busy}
              >
                {!busy && <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
                Confirm disconnect
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onReconnect(app)}
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                Reconnect
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(true)}
                className="text-danger hover:bg-danger-soft"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                Disconnect
              </Button>
            </>
          )
        ) : undefined
      }
    >
      <div className="space-y-5">
        <p className="text-xs leading-relaxed text-ink-secondary">
          {app.description}
        </p>

        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-control border border-danger/20 bg-danger-soft px-3 py-2.5 text-xs text-danger"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {error}
          </div>
        )}

        {confirming && !isStateApp && (
          <div
            role="alert"
            className="rounded-control border border-danger/20 bg-danger-soft px-3 py-2.5 text-xs text-danger"
          >
            This revokes Founder OS&apos;s access at{" "}
            {app.key === "google_calendar" ? "Google" : app.display_name} and
            deletes the stored credentials. Anything that depends on this
            connection stops until you reconnect.
          </div>
        )}

        {isStateApp ? (
          <SourceList
            sources={sources}
            onDisconnect={onDisconnectSource}
            onManage={onManageSources}
          />
        ) : (
          <FieldList fields={app.details} />
        )}
      </div>
    </Dialog>
  );
}
