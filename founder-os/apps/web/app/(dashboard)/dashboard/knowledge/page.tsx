"use client";

import { useState, useEffect, useCallback, useRef, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import {
  BookOpen,
  Plus,
  Search,
  Loader2,
  Trash2,
  FileText,
  FileUp,
  Tag,
  Database,
  ExternalLink,
  X,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Button,
  Input,
  Textarea,
  Tabs,
} from "@/app/_components/ui";

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

/* ── Knowledge page ───────────────────────────────── */
export default function KnowledgePage() {
  const api = useApi();
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showIngest, setShowIngest] = useState(false);
  const [ingestMode, setIngestMode] = useState<"text" | "url" | "file">("text");
  const [ingestTitle, setIngestTitle] = useState("");
  const [ingestContent, setIngestContent] = useState("");
  const [ingestCategory, setIngestCategory] = useState("");
  const [ingestFile, setIngestFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<string | null>(null);
  // Seed from a ?q=<query> deep link (command palette hand-off).
  const [searchQuery, setSearchQuery] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const didAutoSearch = useRef(false);
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
      } else if (ingestMode === "url") {
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
      } else {
        if (!ingestFile) return;
        const formData = new FormData();
        formData.append("file", ingestFile);
        if (ingestTitle.trim()) formData.append("title", ingestTitle.trim());
        if (ingestCategory.trim()) formData.append("category", ingestCategory.trim());
        const data = await api("/api/knowledge/ingest/file", {
          method: "POST",
          body: formData,
          timeoutMs: 120_000, // PDFs take longer to extract + embed
        });
        setIngestResult(
          `Uploaded ${ingestFile.name}: ${data.chunks_created} chunks (${data.total_tokens} tokens)`
        );
        setIngestFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
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

  const runSearch = useCallback(
    async (rawQuery: string) => {
      const query = rawQuery.trim();
      if (!query) return;
      setSearching(true);
      try {
        const data = await api("/api/knowledge/search", {
          method: "POST",
          body: JSON.stringify({ query, limit: 10 }),
        });
        setSearchResults(data.results || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    },
    [api]
  );

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    if (searching) return;
    void runSearch(searchQuery);
  };

  // Auto-run the search once when arriving via a ?q= deep link.
  useEffect(() => {
    if (didAutoSearch.current) return;
    didAutoSearch.current = true;
    if (searchQuery.trim()) void runSearch(searchQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runSearch]);

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

  const ingestTabs = [
    { id: "text", label: "Text" },
    { id: "url", label: "URL" },
    { id: "file", label: "File / PDF" },
  ];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Knowledge"
        description="Documents and data your agents can reference"
        actions={
          <Button
            variant={showIngest ? "secondary" : "primary"}
            onClick={() => setShowIngest(!showIngest)}
          >
            {showIngest ? (
              <X className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            {showIngest ? "Cancel" : "Add knowledge"}
          </Button>
        }
      />

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total items", value: stats.total_items, icon: Database },
            { label: "With embeddings", value: stats.items_with_embeddings, icon: FileText },
            { label: "Pending", value: stats.items_without_embeddings, icon: Loader2 },
            { label: "Model", value: stats.embedding_model.split("/").pop() || stats.embedding_model, icon: Tag },
          ].map((s) => (
            <Card key={s.label} className="p-3">
              <div className="mb-1 flex items-center gap-2 text-xs text-ink-secondary">
                <s.icon className="h-3.5 w-3.5" aria-hidden="true" />
                {s.label}
              </div>
              <p className="truncate text-lg font-semibold text-ink">{s.value}</p>
            </Card>
          ))}
        </div>
      )}

      {/* Ingest panel */}
      {showIngest && (
        <Card className="p-5">
          <div className="mb-4">
            <Tabs
              tabs={ingestTabs}
              active={ingestMode}
              onChange={(id) => setIngestMode(id as "text" | "url" | "file")}
            />
          </div>
          <form onSubmit={handleIngest} className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Input
                type="text"
                value={ingestTitle}
                onChange={(e) => setIngestTitle(e.target.value)}
                placeholder="Title (optional)"
                aria-label="Title"
              />
              <Input
                type="text"
                value={ingestCategory}
                onChange={(e) => setIngestCategory(e.target.value)}
                placeholder="Category (optional)"
                aria-label="Category"
              />
            </div>
            {ingestMode === "text" ? (
              <Textarea
                value={ingestContent}
                onChange={(e) => setIngestContent(e.target.value)}
                placeholder="Paste your text content here"
                aria-label="Text content"
                rows={5}
              />
            ) : ingestMode === "url" ? (
              <Input
                type="url"
                value={ingestContent}
                onChange={(e) => setIngestContent(e.target.value)}
                placeholder="https://example.com/article"
                aria-label="URL"
              />
            ) : (
              <div>
                <label
                  htmlFor="knowledge-file-input"
                  className="flex w-full cursor-pointer items-center gap-3 rounded-control border border-dashed border-line bg-surface-muted/40 px-3 py-4 text-sm transition-colors duration-150 hover:border-ink-muted"
                >
                  <FileUp className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
                  {ingestFile ? (
                    <span className="truncate text-ink">
                      {ingestFile.name}{" "}
                      <span className="text-ink-secondary">
                        ({(ingestFile.size / 1024).toFixed(0)} KB)
                      </span>
                    </span>
                  ) : (
                    <span className="text-ink-secondary">
                      Choose a PDF, TXT, MD, CSV or JSON file (max 10 MB)
                    </span>
                  )}
                </label>
                <input
                  id="knowledge-file-input"
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.md,.csv,.json,application/pdf,text/plain,text/markdown,text/csv,application/json"
                  onChange={(e) => setIngestFile(e.target.files?.[0] ?? null)}
                  className="sr-only"
                />
              </div>
            )}
            <div className="flex items-center gap-3">
              <Button
                type="submit"
                disabled={
                  ingestMode === "file" ? !ingestFile : !ingestContent.trim()
                }
                loading={ingesting}
              >
                {ingesting ? "Ingesting" : "Ingest"}
              </Button>
              {ingestResult && (
                <span className="text-sm text-ink-secondary">{ingestResult}</span>
              )}
            </div>
          </form>
        </Card>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
            aria-hidden="true"
          />
          <Input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search your knowledge base"
            aria-label="Search knowledge base"
            className="pl-10"
          />
        </div>
        <Button type="submit" disabled={!searchQuery.trim()} loading={searching}>
          {searching ? "Searching" : "Search"}
        </Button>
      </form>

      {/* Search results */}
      {searchResults && (
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-serif text-lg font-semibold text-ink">
              Search results ({searchResults.length})
            </h2>
            <button
              type="button"
              onClick={() => setSearchResults(null)}
              className="text-xs text-ink-secondary hover:underline"
            >
              Clear
            </button>
          </div>
          {searchResults.length === 0 ? (
            <p className="py-4 text-center text-sm text-ink-secondary">
              No results found.
            </p>
          ) : (
            <div className="space-y-3">
              {searchResults.map((r) => (
                <div
                  key={r.id}
                  className="rounded-control border border-line bg-surface-muted/40 p-3"
                >
                  <div className="mb-1 flex items-start justify-between">
                    <p className="text-sm font-medium text-ink">{r.title || "Untitled"}</p>
                    <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-ink-secondary">
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                  </div>
                  <p className="line-clamp-2 text-xs text-ink-secondary">
                    {r.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Items list */}
      <Card className="p-5">
        <h2 className="mb-4 font-serif text-lg font-semibold text-ink">
          Knowledge items {!loading && `(${items.length})`}
        </h2>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-ink-muted" aria-hidden="true" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center">
            <BookOpen
              className="mx-auto mb-3 h-10 w-10 text-ink-muted"
              strokeWidth={1.5}
              aria-hidden="true"
            />
            <h3 className="mb-2 font-serif text-lg font-semibold text-ink">
              No documents yet
            </h3>
            <p className="mx-auto max-w-sm text-sm text-ink-secondary">
              Upload documents, notes, or links to give your agents something to
              ground their work in.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                className="rounded-control border border-line p-3 transition-colors duration-150 hover:bg-surface-muted/40"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-4 w-4 shrink-0 text-ink-secondary" aria-hidden="true" />
                  <button
                    type="button"
                    onClick={() => setExpandedItem(expandedItem === item.id ? null : item.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="truncate text-sm font-medium text-ink">
                      {item.title || "Untitled"}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-secondary">
                      {item.category && (
                        <span className="rounded bg-surface-muted px-1.5 py-0.5">
                          {item.category}
                        </span>
                      )}
                      <span>{new Date(item.created_at).toLocaleDateString()}</span>
                      <span>{item.has_embedding ? "Embedded" : "Pending"}</span>
                    </div>
                  </button>
                  {item.source_url && (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="Open source"
                      className="p-1.5 text-ink-muted transition-colors duration-150 hover:text-ink"
                    >
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDelete(item.id)}
                    disabled={deleting === item.id}
                    aria-label="Delete item"
                    className="p-1.5 text-ink-muted transition-colors duration-150 hover:text-danger"
                  >
                    {deleting === item.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                  </button>
                </div>
                {expandedItem === item.id && (
                  <div className="mt-3 border-t border-line-subtle pt-3">
                    <p className="line-clamp-10 whitespace-pre-wrap text-xs text-ink-secondary">
                      {item.content}
                    </p>
                    {item.tags && item.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {item.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] text-ink-secondary"
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
      </Card>
    </div>
  );
}
