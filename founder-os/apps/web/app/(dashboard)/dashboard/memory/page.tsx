"use client";

import { useState, useEffect, useCallback, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import {
  Brain,
  Search,
  Loader2,
  Pin,
  Trash2,
  BookOpen,
  Hash,
  Clock,
  Star,
  ChevronDown,
  ChevronUp,
  Database,
  TrendingUp,
  Layers,
  Plus,
  X,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface MemoryEntry {
  id: string;
  title: string;
  content: string;
  summary: string | null;
  page_type: string;
  chapter: string | null;
  tags: string[];
  entities: Record<string, string[]>;
  occurred_at: string | null;
  importance: number;
  is_pinned: boolean;
  source: string;
  scores?: {
    composite: number;
    semantic: number;
    temporal: number;
    importance: number;
    access: number;
  };
}

interface MemoryStats {
  total_memories: number;
  chapters: Record<string, number> | number;
  pinned: number;
  by_type?: Record<string, number>;
  [key: string]: unknown;
}

interface Chapter {
  name: string;
  count: number;
}

/* ── Page Type Badge ──────────────────────────────── */
const typeColors: Record<string, string> = {
  event: "bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400",
  decision: "bg-amber-100 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400",
  milestone: "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
  metric: "bg-purple-100 text-purple-600 dark:bg-purple-500/10 dark:text-purple-400",
  insight: "bg-pink-100 text-pink-600 dark:bg-pink-500/10 dark:text-pink-400",
  note: "bg-gray-100 text-gray-600 dark:bg-gray-500/10 dark:text-gray-400",
};

/* ── Memory Card ──────────────────────────────────── */
function MemoryCard({
  memory,
  expanded,
  onToggle,
  onPin,
  onDelete,
  pinning,
  deleting,
}: {
  memory: MemoryEntry;
  expanded: boolean;
  onToggle: () => void;
  onPin: () => void;
  onDelete: () => void;
  pinning: boolean;
  deleting: boolean;
}) {
  return (
    <div
      className={clsx(
        "p-4 rounded-xl border transition-colors",
        memory.is_pinned
          ? "border-amber-300 dark:border-amber-500/30 bg-amber-50/50 dark:bg-amber-500/5"
          : "border-[var(--color-border)] hover:bg-[var(--color-surface-subtle)]"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {memory.is_pinned ? (
            <Pin className="w-4 h-4 text-amber-500" />
          ) : (
            <Brain className="w-4 h-4 text-indigo-500" />
          )}
        </div>
        <button onClick={onToggle} className="flex-1 text-left min-w-0">
          <p className="text-sm font-medium">{memory.title}</p>
          {memory.summary && (
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 line-clamp-1">
              {memory.summary}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span
              className={clsx(
                "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                typeColors[memory.page_type] || typeColors.note
              )}
            >
              {memory.page_type}
            </span>
            {memory.chapter && (
              <span className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-0.5">
                <BookOpen className="w-3 h-3" />
                {memory.chapter}
              </span>
            )}
            {memory.occurred_at && (
              <span className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-0.5">
                <Clock className="w-3 h-3" />
                {new Date(memory.occurred_at).toLocaleDateString()}
              </span>
            )}
            <span className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-0.5">
              <Star className="w-3 h-3" />
              {(memory.importance * 100).toFixed(0)}%
            </span>
          </div>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onPin}
            disabled={pinning}
            className={clsx(
              "p-1.5 rounded-lg transition-colors",
              memory.is_pinned
                ? "text-amber-500 hover:bg-amber-100 dark:hover:bg-amber-500/10"
                : "text-[var(--color-text-muted)] hover:text-amber-500 hover:bg-[var(--color-surface-subtle)]"
            )}
            title={memory.is_pinned ? "Unpin" : "Pin"}
          >
            {pinning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Pin className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-red-500 hover:bg-[var(--color-surface-subtle)] transition-colors"
          >
            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border)] space-y-2">
          <p className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap">
            {memory.content}
          </p>
          {memory.tags.length > 0 && (
            <div className="flex gap-1.5 flex-wrap">
              {memory.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400 flex items-center gap-0.5"
                >
                  <Hash className="w-2.5 h-2.5" />
                  {tag}
                </span>
              ))}
            </div>
          )}
          {memory.scores && (
            <div className="flex gap-3 text-[10px] text-[var(--color-text-muted)]">
              <span>Composite: {memory.scores.composite.toFixed(2)}</span>
              <span>Semantic: {memory.scores.semantic.toFixed(2)}</span>
              <span>Temporal: {memory.scores.temporal.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Memory Page ──────────────────────────────────── */
export default function MemoryPage() {
  const api = useApi();
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [selectedChapter, setSelectedChapter] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [pinningId, setPinningId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showStore, setShowStore] = useState(false);
  const [storeTitle, setStoreTitle] = useState("");
  const [storeContent, setStoreContent] = useState("");
  const [storeType, setStoreType] = useState("note");
  const [storeChapter, setStoreChapter] = useState("");
  const [storing, setStoring] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statsData, chaptersData, recallData] = await Promise.all([
        api("/api/memory/stats").catch(() => null),
        api("/api/memory/chapters").catch(() => ({ chapters: [] })),
        api("/api/memory/recall", {
          method: "POST",
          body: JSON.stringify({ limit: 20 }),
        }).catch(() => ({ results: [] })),
      ]);
      if (statsData) setStats(statsData);
      if (chaptersData?.chapters) {
        const ch = Array.isArray(chaptersData.chapters)
          ? chaptersData.chapters
          : Object.entries(chaptersData.chapters).map(([name, count]) => ({
              name,
              count: count as number,
            }));
        setChapters(ch);
      }
      if (recallData?.results) setMemories(recallData.results);
    } catch {
      // backend not ready
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRecall = async (e?: FormEvent) => {
    e?.preventDefault();
    setSearching(true);
    try {
      const body: Record<string, unknown> = { limit: 30 };
      if (query.trim()) body.query = query.trim();
      if (selectedChapter) body.chapter = selectedChapter;
      const data = await api("/api/memory/recall", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMemories(data.results || []);
    } catch {
      // ignore
    } finally {
      setSearching(false);
    }
  };

  const handlePin = async (id: string, currentlyPinned: boolean) => {
    setPinningId(id);
    try {
      await api(`/api/memory/pin/${id}?pin=${!currentlyPinned}`, {
        method: "POST",
      });
      setMemories((prev) =>
        prev.map((m) => (m.id === id ? { ...m, is_pinned: !currentlyPinned } : m))
      );
    } catch {
      // ignore
    } finally {
      setPinningId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await api(`/api/memory/${id}`, { method: "DELETE" });
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch {
      // ignore
    } finally {
      setDeletingId(null);
    }
  };

  const handleStore = async (e: FormEvent) => {
    e.preventDefault();
    if (!storeTitle.trim() || !storeContent.trim() || storing) return;
    setStoring(true);
    try {
      await api("/api/memory/store", {
        method: "POST",
        body: JSON.stringify({
          title: storeTitle.trim(),
          content: storeContent.trim(),
          page_type: storeType,
          chapter: storeChapter.trim() || undefined,
        }),
      });
      setStoreTitle("");
      setStoreContent("");
      setStoreChapter("");
      setShowStore(false);
      fetchData();
    } catch {
      // ignore
    } finally {
      setStoring(false);
    }
  };

  const totalMemories =
    typeof stats?.total_memories === "number" ? stats.total_memories : 0;
  const pinnedCount =
    typeof stats?.pinned === "number" ? stats.pinned : 0;
  const chapterCount = chapters.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Your AI&apos;s long-term memory and context
          </p>
        </div>
        <button
          onClick={() => setShowStore(!showStore)}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all"
        >
          {showStore ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showStore ? "Cancel" : "Add Memory"}
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-1">
            <Database className="w-3.5 h-3.5" />
            Total Memories
          </div>
          <p className="text-lg font-bold">{loading ? "—" : totalMemories}</p>
        </div>
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-1">
            <Pin className="w-3.5 h-3.5" />
            Pinned
          </div>
          <p className="text-lg font-bold">{loading ? "—" : pinnedCount}</p>
        </div>
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-1">
            <Layers className="w-3.5 h-3.5" />
            Chapters
          </div>
          <p className="text-lg font-bold">{loading ? "—" : chapterCount}</p>
        </div>
      </div>

      {/* Store Form */}
      {showStore && (
        <form
          onSubmit={handleStore}
          className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-5 space-y-3"
        >
          <h3 className="text-sm font-semibold">Store a New Memory</h3>
          <input
            type="text"
            value={storeTitle}
            onChange={(e) => setStoreTitle(e.target.value)}
            placeholder="What happened?"
            className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-indigo-400 placeholder:text-[var(--color-text-muted)]"
          />
          <textarea
            value={storeContent}
            onChange={(e) => setStoreContent(e.target.value)}
            placeholder="Full details..."
            rows={3}
            className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-indigo-400 resize-none placeholder:text-[var(--color-text-muted)]"
          />
          <div className="grid grid-cols-2 gap-3">
            <select
              value={storeType}
              onChange={(e) => setStoreType(e.target.value)}
              className="px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none"
            >
              <option value="note">Note</option>
              <option value="event">Event</option>
              <option value="decision">Decision</option>
              <option value="milestone">Milestone</option>
              <option value="metric">Metric</option>
              <option value="insight">Insight</option>
            </select>
            <input
              type="text"
              value={storeChapter}
              onChange={(e) => setStoreChapter(e.target.value)}
              placeholder="Chapter (e.g., product, hiring)"
              className="px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-indigo-400 placeholder:text-[var(--color-text-muted)]"
            />
          </div>
          <button
            type="submit"
            disabled={!storeTitle.trim() || !storeContent.trim() || storing}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {storing ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Storing...
              </span>
            ) : (
              "Store Memory"
            )}
          </button>
        </form>
      )}

      {/* Search & Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <form onSubmit={handleRecall} className="flex gap-2 flex-1">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Recall memories..."
              className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] outline-none focus:border-indigo-400 placeholder:text-[var(--color-text-muted)]"
            />
          </div>
          <button
            type="submit"
            disabled={searching}
            className="px-4 py-2.5 text-sm font-medium text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Recall"}
          </button>
        </form>

        {/* Chapter Filter */}
        {chapters.length > 0 && (
          <div className="flex gap-1.5 items-center flex-wrap">
            <button
              key="__all__"
              onClick={() => {
                setSelectedChapter(null);
                handleRecall();
              }}
              className={clsx(
                "px-2.5 py-1.5 text-xs rounded-lg transition-colors",
                !selectedChapter
                  ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
              )}
            >
              All
            </button>
            {chapters.map((ch) => (
              <button
                key={ch.name}
                onClick={() => {
                  setSelectedChapter(ch.name);
                }}
                className={clsx(
                  "px-2.5 py-1.5 text-xs rounded-lg transition-colors",
                  selectedChapter === ch.name
                    ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
                )}
              >
                {ch.name} ({ch.count})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Memory List */}
      <div className="space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
          </div>
        ) : memories.length === 0 ? (
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] p-12 text-center">
            <Brain className="w-12 h-12 text-[var(--color-text-muted)] mx-auto mb-3" />
            <h2 className="text-lg font-semibold mb-2">No memories yet</h2>
            <p className="text-sm text-[var(--color-text-secondary)] max-w-sm mx-auto">
              Memories are stored automatically as your agents work, or you can
              add them manually.
            </p>
          </div>
        ) : (
          memories.map((m) => (
            <MemoryCard
              key={m.id}
              memory={m}
              expanded={expandedId === m.id}
              onToggle={() => setExpandedId(expandedId === m.id ? null : m.id)}
              onPin={() => handlePin(m.id, m.is_pinned)}
              onDelete={() => handleDelete(m.id)}
              pinning={pinningId === m.id}
              deleting={deletingId === m.id}
            />
          ))
        )}
      </div>
    </div>
  );
}
