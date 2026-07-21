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
  Database,
  Layers,
  Plus,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import {
  PageHeader,
  Card,
  Button,
  Input,
  Textarea,
  Select,
  EmptyState,
} from "@/app/_components/ui";

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

/* ── Memory card ──────────────────────────────────── */
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
        "rounded-card border bg-surface p-4 transition-colors duration-150",
        memory.is_pinned
          ? "border-accent/40 bg-accent-soft/30"
          : "border-line hover:bg-surface-muted/40"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {memory.is_pinned ? (
            <Pin className="h-4 w-4 text-accent-text" aria-hidden="true" />
          ) : (
            <Brain className="h-4 w-4 text-ink-secondary" aria-hidden="true" />
          )}
        </div>
        <button type="button" onClick={onToggle} className="min-w-0 flex-1 text-left">
          <p className="text-sm font-medium text-ink">{memory.title}</p>
          {memory.summary && (
            <p className="mt-0.5 line-clamp-1 text-xs text-ink-secondary">
              {memory.summary}
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-medium text-ink-secondary">
              {memory.page_type}
            </span>
            {memory.chapter && (
              <span className="flex items-center gap-0.5 text-[10px] text-ink-secondary">
                <BookOpen className="h-3 w-3" aria-hidden="true" />
                {memory.chapter}
              </span>
            )}
            {memory.occurred_at && (
              <span className="flex items-center gap-0.5 text-[10px] text-ink-secondary">
                <Clock className="h-3 w-3" aria-hidden="true" />
                {new Date(memory.occurred_at).toLocaleDateString()}
              </span>
            )}
            <span className="flex items-center gap-0.5 text-[10px] text-ink-secondary">
              <Star className="h-3 w-3" aria-hidden="true" />
              {(memory.importance * 100).toFixed(0)}%
            </span>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onPin}
            disabled={pinning}
            className={clsx(
              "rounded-control p-1.5 transition-colors duration-150",
              memory.is_pinned
                ? "text-accent-text hover:bg-surface-muted"
                : "text-ink-muted hover:bg-surface-muted hover:text-ink"
            )}
            title={memory.is_pinned ? "Unpin" : "Pin"}
            aria-label={memory.is_pinned ? "Unpin memory" : "Pin memory"}
          >
            {pinning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Pin className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            aria-label="Delete memory"
            className="rounded-control p-1.5 text-ink-muted transition-colors duration-150 hover:bg-surface-muted hover:text-danger"
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 border-t border-line-subtle pt-3">
          <p className="whitespace-pre-wrap text-xs text-ink-secondary">
            {memory.content}
          </p>
          {memory.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {memory.tags.map((tag) => (
                <span
                  key={tag}
                  className="flex items-center gap-0.5 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] text-ink-secondary"
                >
                  <Hash className="h-2.5 w-2.5" aria-hidden="true" />
                  {tag}
                </span>
              ))}
            </div>
          )}
          {memory.scores && (
            <div className="flex gap-3 text-[10px] text-ink-secondary">
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

/* ── Memory page ──────────────────────────────────── */
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
        }).catch(() => ({ memories: [] })),
      ]);
      if (statsData) setStats(statsData);
      if (chaptersData?.chapters) {
        const ch = Array.isArray(chaptersData.chapters)
          ? chaptersData.chapters.map((c: Record<string, unknown>) => ({
              name: c.chapter ?? c.name,
              count: c.count as number,
            }))
          : Object.entries(chaptersData.chapters).map(([name, count]) => ({
              name,
              count: count as number,
            }));
        setChapters(ch);
      }
      if (recallData?.memories) setMemories(recallData.memories);
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
      setMemories(data.memories || []);
    } catch {
      // ignore
    } finally {
      setSearching(false);
    }
  };

  // Re-fetch when chapter filter changes
  useEffect(() => {
    if (!loading) handleRecall();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChapter]);

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
    if (!confirm("Delete this memory? This cannot be undone.")) return;
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
    <div className="space-y-8">
      <PageHeader
        title="Memory"
        description="Your AI's long-term memory and context"
        actions={
          <Button
            variant={showStore ? "secondary" : "primary"}
            onClick={() => setShowStore(!showStore)}
          >
            {showStore ? (
              <X className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            {showStore ? "Cancel" : "Add memory"}
          </Button>
        }
      />

      {/* Stats row */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          { icon: Database, label: "Total memories", value: totalMemories },
          { icon: Pin, label: "Pinned", value: pinnedCount },
          { icon: Layers, label: "Chapters", value: chapterCount },
        ].map((s) => (
          <Card key={s.label} className="p-3">
            <div className="mb-1 flex items-center gap-2 text-xs text-ink-secondary">
              <s.icon className="h-3.5 w-3.5" aria-hidden="true" />
              {s.label}
            </div>
            <p className="text-lg font-semibold text-ink">{loading ? "—" : s.value}</p>
          </Card>
        ))}
      </div>

      {/* Store form */}
      {showStore && (
        <form onSubmit={handleStore}>
          <Card className="space-y-3 p-5">
            <h3 className="font-serif text-sm font-semibold text-ink">
              Store a new memory
            </h3>
            <Input
              type="text"
              value={storeTitle}
              onChange={(e) => setStoreTitle(e.target.value)}
              placeholder="What happened?"
              aria-label="Memory title"
            />
            <Textarea
              value={storeContent}
              onChange={(e) => setStoreContent(e.target.value)}
              placeholder="Full details"
              aria-label="Memory details"
              rows={3}
            />
            <div className="grid grid-cols-2 gap-3">
              <Select
                value={storeType}
                onChange={(e) => setStoreType(e.target.value)}
                aria-label="Memory type"
              >
                <option value="note">Note</option>
                <option value="event">Event</option>
                <option value="decision">Decision</option>
                <option value="milestone">Milestone</option>
                <option value="metric">Metric</option>
                <option value="insight">Insight</option>
              </Select>
              <Input
                type="text"
                value={storeChapter}
                onChange={(e) => setStoreChapter(e.target.value)}
                placeholder="Chapter (e.g. product, hiring)"
                aria-label="Chapter"
              />
            </div>
            <Button
              type="submit"
              disabled={!storeTitle.trim() || !storeContent.trim()}
              loading={storing}
            >
              {storing ? "Storing" : "Store memory"}
            </Button>
          </Card>
        </form>
      )}

      {/* Search and filter */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <form onSubmit={handleRecall} className="flex flex-1 gap-2">
          <div className="relative flex-1">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
              aria-hidden="true"
            />
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Recall memories"
              aria-label="Search memories"
              className="pl-10"
            />
          </div>
          <Button type="submit" loading={searching}>
            {searching ? "Recalling" : "Recall"}
          </Button>
        </form>

        {/* Chapter filter */}
        {chapters.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              key="__all__"
              type="button"
              onClick={() => {
                setSelectedChapter(null);
              }}
              className={clsx(
                "rounded-control px-2.5 py-1.5 text-xs transition-colors duration-150",
                !selectedChapter
                  ? "bg-surface-muted font-medium text-ink"
                  : "text-ink-secondary hover:bg-surface-muted/60"
              )}
            >
              All
            </button>
            {chapters.map((ch, idx) => (
              <button
                key={`ch-${idx}-${ch.name}`}
                type="button"
                onClick={() => {
                  setSelectedChapter(ch.name);
                }}
                className={clsx(
                  "rounded-control px-2.5 py-1.5 text-xs transition-colors duration-150",
                  selectedChapter === ch.name
                    ? "bg-surface-muted font-medium text-ink"
                    : "text-ink-secondary hover:bg-surface-muted/60"
                )}
              >
                {ch.name} ({ch.count})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Memory list */}
      <div className="space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
          </div>
        ) : memories.length === 0 ? (
          <EmptyState
            icon={Brain}
            title="No memories yet"
            body="They'll accumulate automatically as your agents work, or you can add one yourself."
            action={
              <Button onClick={() => setShowStore(true)}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add memory
              </Button>
            }
          />
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
