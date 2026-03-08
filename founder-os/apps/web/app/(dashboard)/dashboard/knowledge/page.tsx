"use client";

import { useState, useEffect, useCallback, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import {
  BookOpen,
  Plus,
  Search,
  Loader2,
  Trash2,
  Link as LinkIcon,
  FileText,
  Tag,
  Database,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  X,
  Upload,
  Globe,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface KnowledgeItem {
  id: string;
  title: string | null;
  content: string;
  content_type: string | null;
  category: string | null;
  tags: string[] | null;
  source_url: string | null;
  has_embedding: boolean;
  times_referenced: number;
  processing_status: string;
  created_at: string;
}

interface KnowledgeStats {
  total_items: number;
  items_with_embeddings: number;
  items_without_embeddings: number;
  embedding_model: string;
  embedding_dimensions: number;
}

interface SearchResult {
  id: string;
  title: string | null;
  content: string;
  category: string | null;
  tags: string[] | null;
  score: number;
  source_url: string | null;
}

/* ── Knowledge Page ───────────────────────────────── */
export default function KnowledgePage() {
  const api = useApi();
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showIngest, setShowIngest] = useState(false);
  const [ingestMode, setIngestMode] = useState<"text" | "url">("text");
  const [ingestTitle, setIngestTitle] = useState("");
  const [ingestContent, setIngestContent] = useState("");
  const [ingestCategory, setIngestCategory] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [itemsData, statsData] = await Promise.all([
        api("/api/knowledge/items").catch(() => []),
        api("/api/knowledge/stats").catch(() => null),
      ]);
      setItems(Array.isArray(itemsData) ? itemsData : []);
      if (statsData) setStats(statsData);
    } catch {
      // backend not ready
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleIngest = async (e: FormEvent) => {
    e.preventDefault();
    if (ingesting) return;
    setIngesting(true);
    setIngestResult(null);

    try {
      if (ingestMode === "text") {
        if (!ingestContent.trim()) return;
        const data = await api("/api/knowledge/ingest/text", {
          method: "POST",
          body: JSON.stringify({
            content: ingestContent.trim(),
            title: ingestTitle.trim() || null,
            category: ingestCategory.trim() || null,
          }),
        });
        setIngestResult(`Created ${data.chunks_created} chunks (${data.total_tokens} tokens)`);
      } else {
        if (!ingestContent.trim()) return;
        const data = await api("/api/knowledge/ingest/url", {
          method: "POST",
          body: JSON.stringify({
            url: ingestContent.trim(),
            title: ingestTitle.trim() || null,
            category: ingestCategory.trim() || null,
          }),
        });
        setIngestResult(`Ingested from URL: ${data.chunks_created} chunks`);
      }
      setIngestTitle("");
      setIngestContent("");
      setIngestCategory("");
      fetchData();
    } catch (err) {
      setIngestResult(
        err instanceof Error ? `Error: ${err.message}` : "Ingestion failed."
      );
    } finally {
      setIngesting(false);
    }
  };

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim() || searching) return;
    setSearching(true);
    try {
      const data = await api("/api/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query: searchQuery.trim(), limit: 10 }),
      });
      setSearchResults(data.results || []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this knowledge item? This cannot be undone.")) return;
    setDeleting(id);
    try {
      await api(`/api/knowledge/items/${id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Documents and data your agents can reference
          </p>
        </div>
        <button
          onClick={() => setShowIngest(!showIngest)}
          className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors"
        >
          {showIngest ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showIngest ? "Cancel" : "Add Knowledge"}
        </button>
      </div>

      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Total Items", value: stats.total_items, icon: Database },
            { label: "With Embeddings", value: stats.items_with_embeddings, icon: FileText },
            { label: "Pending", value: stats.items_without_embeddings, icon: Loader2 },
            { label: "Model", value: stats.embedding_model.split("/").pop() || stats.embedding_model, icon: Tag },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-3"
            >
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] mb-1">
                <s.icon className="w-3.5 h-3.5" />
                {s.label}
              </div>
              <p className="text-lg font-bold">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Ingest Panel */}
      {showIngest && (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setIngestMode("text")}
              className={clsx(
                "flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors",
                ingestMode === "text"
                  ? "bg-[var(--color-surface-muted)] text-[var(--color-text)] font-medium"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
              )}
            >
              <Upload className="w-3.5 h-3.5" />
              Text
            </button>
            <button
              onClick={() => setIngestMode("url")}
              className={clsx(
                "flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors",
                ingestMode === "url"
                  ? "bg-[var(--color-surface-muted)] text-[var(--color-text)] font-medium"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
              )}
            >
              <Globe className="w-3.5 h-3.5" />
              URL
            </button>
          </div>
          <form onSubmit={handleIngest} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                type="text"
                value={ingestTitle}
                onChange={(e) => setIngestTitle(e.target.value)}
                placeholder="Title (optional)"
                className="px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] placeholder:text-[var(--color-text-muted)]"
              />
              <input
                type="text"
                value={ingestCategory}
                onChange={(e) => setIngestCategory(e.target.value)}
                placeholder="Category (optional)"
                className="px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] placeholder:text-[var(--color-text-muted)]"
              />
            </div>
            {ingestMode === "text" ? (
              <textarea
                value={ingestContent}
                onChange={(e) => setIngestContent(e.target.value)}
                placeholder="Paste your text content here..."
                rows={5}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] resize-none placeholder:text-[var(--color-text-muted)]"
              />
            ) : (
              <input
                type="url"
                value={ingestContent}
                onChange={(e) => setIngestContent(e.target.value)}
                placeholder="https://example.com/article"
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-subtle)] outline-none focus:border-[var(--color-text-muted)] placeholder:text-[var(--color-text-muted)]"
              />
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={!ingestContent.trim() || ingesting}
                className="px-4 py-2 text-sm font-medium text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
              >
                {ingesting ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Ingesting...
                  </span>
                ) : (
                  "Ingest"
                )}
              </button>
              {ingestResult && (
                <span className="text-sm text-[var(--color-text-secondary)]">{ingestResult}</span>
              )}
            </div>
          </form>
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search your knowledge base..."
            className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] outline-none focus:border-[var(--color-text-muted)] placeholder:text-[var(--color-text-muted)]"
          />
        </div>
        <button
          type="submit"
          disabled={!searchQuery.trim() || searching}
          className="px-4 py-2.5 text-sm font-medium text-[var(--color-accent-foreground)] bg-[var(--color-accent)] rounded-lg hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
        </button>
      </form>

      {/* Search Results */}
      {searchResults && (
        <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">Search Results ({searchResults.length})</h2>
            <button
              onClick={() => setSearchResults(null)}
              className="text-xs text-[var(--color-text-muted)] hover:underline"
            >
              Clear
            </button>
          </div>
          {searchResults.length === 0 ? (
            <p className="text-sm text-[var(--color-text-secondary)] py-4 text-center">
              No results found.
            </p>
          ) : (
            <div className="space-y-3">
              {searchResults.map((r) => (
                <div
                  key={r.id}
                  className="p-3 rounded-lg bg-[var(--color-surface-subtle)] border border-[var(--color-border)]"
                >
                  <div className="flex items-start justify-between mb-1">
                    <p className="text-sm font-medium">{r.title || "Untitled"}</p>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-medium">
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2">
                    {r.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Items List */}
      <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] p-5">
        <h2 className="text-lg font-semibold mb-4">
          Knowledge Items {!loading && `(${items.length})`}
        </h2>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-[var(--color-text-muted)]" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center">
            <BookOpen className="w-12 h-12 text-[var(--color-text-muted)] mx-auto mb-3" />
            <h3 className="text-lg font-semibold mb-2">No documents yet</h3>
            <p className="text-sm text-[var(--color-text-secondary)] max-w-sm mx-auto">
              Upload documents, notes, or links to build your knowledge base.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                className="p-3 rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-surface-subtle)] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FileText className="w-4 h-4 text-[var(--color-text-secondary)] shrink-0" />
                  <button
                    onClick={() => setExpandedItem(expandedItem === item.id ? null : item.id)}
                    className="flex-1 text-left min-w-0"
                  >
                    <p className="text-sm font-medium truncate">{item.title || "Untitled"}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {item.category && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)]">
                          {item.category}
                        </span>
                      )}
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        {item.has_embedding ? "Embedded" : "Pending"}
                      </span>
                    </div>
                  </button>
                  {item.source_url && (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                  <button
                    onClick={() => handleDelete(item.id)}
                    disabled={deleting === item.id}
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors"
                  >
                    {deleting === item.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
                {expandedItem === item.id && (
                  <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
                    <p className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap line-clamp-10">
                      {item.content}
                    </p>
                    {item.tags && item.tags.length > 0 && (
                      <div className="flex gap-1.5 mt-2 flex-wrap">
                        {item.tags.map((tag) => (
                          <span
                            key={tag}
                            className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
