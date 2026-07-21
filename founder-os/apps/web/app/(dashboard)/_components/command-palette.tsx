"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { clsx } from "clsx";
import {
  Search,
  Sparkles,
  CornerDownLeft,
  Clock,
  ListTodo,
  BookOpen,
  Lightbulb,
  Zap,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";
import { useApi } from "@/lib/use-api";
import { Kbd } from "@/app/_components/ui";
import { navGroups, bottomNav, type NavItem } from "./sidebar";

/* ── Types ─────────────────────────────────────────── */

type ResultType = "task" | "knowledge" | "content_idea" | "workflow";

type SearchResult = {
  type: ResultType;
  id: string;
  title: string;
  snippet: string | null;
  meta: string | null;
  updated_at: string | null;
};

/** One selectable row. `index` is assigned when the flat list is built. */
type PaletteItem =
  | { kind: "page"; key: string; label: string; icon: LucideIcon; href: string }
  | { kind: "recent"; key: string; query: string }
  | { kind: "ask"; key: string; query: string }
  | { kind: "result"; key: string; result: SearchResult };

const RECENTS_KEY = "fos-recent-searches";
const MAX_RECENTS = 5;
const DEBOUNCE_MS = 200;

const RESULT_META: Record<
  ResultType,
  { label: string; icon: LucideIcon; href: (r: SearchResult) => string }
> = {
  task: {
    label: "Tasks",
    icon: ListTodo,
    href: (r) => `/dashboard/tasks?task=${r.id}`,
  },
  knowledge: {
    label: "Knowledge",
    icon: BookOpen,
    // Deep-link into the knowledge page's own hybrid search.
    href: (r) => `/dashboard/knowledge?q=${encodeURIComponent(r.title)}`,
  },
  content_idea: {
    label: "Content ideas",
    icon: Lightbulb,
    href: () => `/dashboard/content-ideas`,
  },
  workflow: {
    label: "Automations",
    icon: Zap,
    href: () => `/dashboard/workflows`,
  },
};

const RESULT_ORDER: ResultType[] = [
  "task",
  "knowledge",
  "content_idea",
  "workflow",
];

/* ── Recent-search persistence ─────────────────────── */

function loadRecents(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_RECENTS) : [];
  } catch {
    return [];
  }
}

function pushRecent(query: string): string[] {
  const q = query.trim();
  if (!q) return loadRecents();
  const next = [q, ...loadRecents().filter((r) => r !== q)].slice(0, MAX_RECENTS);
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    /* ignore quota / private-mode failures */
  }
  return next;
}

/* ── Page index (reused from the sidebar nav) ──────── */

const ALL_PAGES: NavItem[] = [
  ...navGroups.flatMap((g) => g.items),
  ...bottomNav,
];

/** Subsequence match, e.g. "kb" → "Knowledge base". Case-insensitive. */
function pageMatches(name: string, q: string): boolean {
  const hay = name.toLowerCase();
  const needle = q.toLowerCase();
  if (hay.includes(needle)) return true;
  let i = 0;
  for (const ch of hay) {
    if (ch === needle[i]) i++;
    if (i === needle.length) return true;
  }
  return false;
}

/* ── Component ─────────────────────────────────────── */

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const api = useApi();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [recents, setRecents] = useState<string[]>([]);

  const trimmed = query.trim();

  /* Global ⌘K / Ctrl+K toggle — always registered while mounted. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  /* On open: reset, focus, load recents. On close: clear transient state. */
  useEffect(() => {
    if (open) {
      setRecents(loadRecents());
      setActiveIndex(0);
      // Focus after paint so the browser doesn't swallow it.
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      setQuery("");
      setResults([]);
      setLoading(false);
    }
  }, [open]);

  /* Debounced server search (≥2 chars), stale responses aborted. */
  useEffect(() => {
    if (!open) return;
    if (trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const data = await api(
          `/api/search?q=${encodeURIComponent(trimmed)}`,
          { signal: controller.signal }
        );
        if (!controller.signal.aborted) setResults(data.results ?? []);
      } catch {
        // apiFetch rewraps AbortError as a plain Error, so key off the
        // controller, not the error type — a stale request must not clobber.
        if (!controller.signal.aborted) setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      clearTimeout(t);
    };
  }, [trimmed, open, api]);

  /* Build the flat, ordered list of selectable items. */
  const items = useMemo<PaletteItem[]>(() => {
    const out: PaletteItem[] = [];

    if (!trimmed) {
      recents.forEach((q, i) =>
        out.push({ kind: "recent", key: `recent-${i}`, query: q })
      );
      ALL_PAGES.forEach((p) =>
        out.push({
          kind: "page",
          key: `page-${p.href}`,
          label: p.name,
          icon: p.icon,
          href: p.href,
        })
      );
      return out;
    }

    ALL_PAGES.filter((p) => pageMatches(p.name, trimmed)).forEach((p) =>
      out.push({
        kind: "page",
        key: `page-${p.href}`,
        label: p.name,
        icon: p.icon,
        href: p.href,
      })
    );
    out.push({ kind: "ask", key: "ask", query: trimmed });
    RESULT_ORDER.forEach((type) => {
      results
        .filter((r) => r.type === type)
        .forEach((r) =>
          out.push({ kind: "result", key: `result-${r.type}-${r.id}`, result: r })
        );
    });
    return out;
  }, [trimmed, recents, results]);

  /* Keep activeIndex in range as the list changes. */
  useEffect(() => {
    setActiveIndex((i) => (items.length === 0 ? 0 : Math.min(i, items.length - 1)));
  }, [items.length]);

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  const runItem = useCallback(
    (item: PaletteItem | undefined) => {
      if (!item) return;
      switch (item.kind) {
        case "page":
          router.push(item.href);
          close();
          break;
        case "recent":
          setQuery(item.query);
          requestAnimationFrame(() => inputRef.current?.focus());
          break;
        case "ask":
          // Hand the query to the Chat page's prefill hook.
          sessionStorage.setItem("fos-pending-chat-prompt", item.query);
          setRecents(pushRecent(item.query));
          router.push("/dashboard/chat");
          close();
          break;
        case "result": {
          const { result } = item;
          setRecents(pushRecent(trimmed));
          router.push(RESULT_META[result.type].href(result));
          close();
          break;
        }
      }
    },
    [router, close, trimmed]
  );

  /* Keyboard navigation within the palette. */
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) =>
        items.length ? (i - 1 + items.length) % items.length : 0
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      runItem(items[activeIndex]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  };

  /* Scroll the active row into view. */
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${activeIndex}"]`
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  if (!open) return null;

  const showEmpty =
    trimmed.length >= 2 && !loading && items.filter((i) => i.kind === "result").length === 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]"
      role="presentation"
    >
      <button
        type="button"
        aria-label="Close search"
        className="absolute inset-0 cursor-default bg-ink/30 backdrop-blur-sm"
        onClick={close}
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search Founder OS"
        className="relative flex w-full max-w-xl flex-col overflow-hidden rounded-card border border-line bg-surface shadow-2xl motion-safe:animate-[fadeInScale_120ms_ease-out]"
      >
        {/* Input row */}
        <div className="flex items-center gap-3 border-b border-line-subtle px-4">
          <Search
            className="h-4 w-4 shrink-0 text-ink-muted"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={
              items[activeIndex] ? `cmdk-opt-${activeIndex}` : undefined
            }
            aria-autocomplete="list"
            placeholder="Search tasks, docs, ideas, automations — or ask the Orchestrator"
            className="h-12 w-full bg-transparent text-sm text-ink placeholder:text-ink-muted focus:outline-none"
          />
          <Kbd>Esc</Kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          id="command-palette-list"
          role="listbox"
          aria-label="Search results"
          className="max-h-[52vh] overflow-y-auto py-2"
        >
          <Rows
            items={items}
            activeIndex={activeIndex}
            loading={loading}
            hasQuery={trimmed.length > 0}
            queryTooShort={trimmed.length === 1}
            showEmpty={showEmpty}
            onHover={setActiveIndex}
            onRun={runItem}
            query={trimmed}
          />
        </div>

        {/* Footer hints */}
        <div className="flex items-center gap-4 border-t border-line-subtle px-4 py-2.5 text-[11px] text-ink-muted">
          <span className="flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            to navigate
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd>
            to select
          </span>
          <span className="ml-auto flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            Enter without a match asks the AI
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Rows renderer (grouped headings over the flat list) ── */

function Rows({
  items,
  activeIndex,
  loading,
  hasQuery,
  queryTooShort,
  showEmpty,
  onHover,
  onRun,
  query,
}: {
  items: PaletteItem[];
  activeIndex: number;
  loading: boolean;
  hasQuery: boolean;
  queryTooShort: boolean;
  showEmpty: boolean;
  onHover: (i: number) => void;
  onRun: (item: PaletteItem) => void;
  query: string;
}) {
  const rows: React.ReactNode[] = [];
  let lastGroup = "";

  const heading = (label: string) => (
    <div
      key={`h-${label}`}
      className="px-4 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wide text-ink-muted first:pt-1"
    >
      {label}
    </div>
  );

  items.forEach((item, i) => {
    const group = groupLabel(item);
    if (group !== lastGroup) {
      rows.push(heading(group));
      lastGroup = group;
    }
    rows.push(
      <Row
        key={item.key}
        item={item}
        index={i}
        active={i === activeIndex}
        onHover={onHover}
        onRun={onRun}
        query={query}
      />
    );
  });

  return (
    <>
      {rows}
      {loading && (
        <div className="px-4 py-3 text-sm text-ink-muted">Searching…</div>
      )}
      {queryTooShort && !loading && (
        <div className="px-4 py-3 text-sm text-ink-muted">
          Keep typing to search your workspace…
        </div>
      )}
      {showEmpty && (
        <div className="px-4 py-3 text-sm text-ink-secondary">
          No matches in your workspace.{" "}
          <span className="text-ink-muted">
            Press <Kbd>↵</Kbd> to ask the Orchestrator instead.
          </span>
        </div>
      )}
      {!hasQuery && items.length === 0 && (
        <div className="px-4 py-3 text-sm text-ink-muted">
          Type to search, or jump to a page.
        </div>
      )}
    </>
  );
}

function groupLabel(item: PaletteItem): string {
  switch (item.kind) {
    case "recent":
      return "Recent";
    case "page":
      return "Go to";
    case "ask":
      return "Ask";
    case "result":
      return RESULT_META[item.result.type].label;
  }
}

/* ── Single row ────────────────────────────────────── */

function Row({
  item,
  index,
  active,
  onHover,
  onRun,
  query,
}: {
  item: PaletteItem;
  index: number;
  active: boolean;
  onHover: (i: number) => void;
  onRun: (item: PaletteItem) => void;
  query: string;
}) {
  return (
    <button
      type="button"
      id={`cmdk-opt-${index}`}
      data-index={index}
      role="option"
      aria-selected={active}
      onMouseMove={() => onHover(index)}
      onClick={() => onRun(item)}
      className={clsx(
        "flex w-full items-center gap-3 px-4 py-2 text-left transition-colors duration-100",
        active ? "bg-surface-muted" : "bg-transparent"
      )}
    >
      <RowIcon item={item} active={active} />
      <div className="min-w-0 flex-1">
        <RowLabel item={item} query={query} />
        <RowSnippet item={item} />
      </div>
      <RowTrailing item={item} active={active} />
    </button>
  );
}

function RowIcon({ item, active }: { item: PaletteItem; active: boolean }) {
  const cls = clsx("h-4 w-4 shrink-0", active ? "text-accent" : "text-ink-muted");
  if (item.kind === "page")
    return <item.icon className={cls} aria-hidden="true" />;
  if (item.kind === "recent")
    return <Clock className={cls} aria-hidden="true" />;
  if (item.kind === "ask")
    return <Sparkles className={cls} aria-hidden="true" />;
  const Icon = RESULT_META[item.result.type].icon;
  return <Icon className={cls} aria-hidden="true" />;
}

function RowLabel({ item, query }: { item: PaletteItem; query: string }) {
  if (item.kind === "page")
    return <div className="truncate text-sm text-ink">{item.label}</div>;
  if (item.kind === "recent")
    return <div className="truncate text-sm text-ink">{item.query}</div>;
  if (item.kind === "ask")
    return (
      <div className="truncate text-sm text-ink">
        Ask the Orchestrator:{" "}
        <span className="text-ink-secondary">“{item.query}”</span>
      </div>
    );
  return (
    <div className="truncate text-sm text-ink">
      {highlight(item.result.title, query)}
    </div>
  );
}

function RowSnippet({ item }: { item: PaletteItem }) {
  if (item.kind !== "result" || !item.result.snippet) return null;
  return (
    <div className="truncate text-xs text-ink-muted">{item.result.snippet}</div>
  );
}

function RowTrailing({ item, active }: { item: PaletteItem; active: boolean }) {
  if (item.kind === "result" && item.result.meta) {
    return (
      <span className="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium capitalize text-ink-secondary">
        {item.result.meta}
      </span>
    );
  }
  if (item.kind === "page" || item.kind === "ask") {
    return active ? (
      <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
    ) : (
      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-transparent" aria-hidden="true" />
    );
  }
  return null;
}

/* Bold the matched substring in a result title. */
function highlight(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-transparent font-semibold text-ink">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}
