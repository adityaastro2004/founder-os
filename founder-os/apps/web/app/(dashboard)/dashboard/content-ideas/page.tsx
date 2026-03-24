"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { DIRECT_API_URL } from "@/lib/api";
import {
  Lightbulb,
  Loader2,
  Sparkles,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Target,
  Users,
  Tag,
  BarChart2,
  FileText,
} from "lucide-react";
import { clsx } from "clsx";

/* ── Types ─────────────────────────────────────────── */
interface ContentIdea {
  id: string;
  title: string;
  description?: string;
  content_type?: string;
  target_audience?: string;
  hooks: string[];
  key_points: string[];
  source_type?: string;
  priority: number;
  status: string;
  created_at: string;
}

/* ── Content Idea Card ─────────────────────────────── */
function IdeaCard({ idea }: { idea: ContentIdea }) {
  const [expanded, setExpanded] = useState(false);

  const priorityColor =
    idea.priority >= 8
      ? "bg-green-50 text-green-700 border-green-200"
      : idea.priority >= 5
      ? "bg-yellow-50 text-yellow-700 border-yellow-200"
      : "bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)] border-[var(--color-border)]";

  return (
    <div className="bg-white rounded-lg border border-[var(--color-border-subtle)] overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-5 py-4 hover:bg-[var(--color-surface-subtle)] transition-colors"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              {idea.content_type && (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] uppercase tracking-wider">
                  <Tag className="w-2.5 h-2.5" />
                  {idea.content_type}
                </span>
              )}
              <span
                className={clsx(
                  "inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border",
                  priorityColor
                )}
              >
                <BarChart2 className="w-2.5 h-2.5" />
                Priority {idea.priority}/10
              </span>
            </div>
            <p className="text-sm font-semibold leading-snug">{idea.title}</p>
            {idea.target_audience && (
              <p className="text-xs text-[var(--color-text-muted)] mt-1 flex items-center gap-1">
                <Users className="w-3 h-3" />
                {idea.target_audience}
              </p>
            )}
          </div>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-[var(--color-text-muted)] shrink-0 mt-0.5" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[var(--color-text-muted)] shrink-0 mt-0.5" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-[var(--color-border-subtle)]">
          {idea.description && (
            <div className="pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                Description
              </p>
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                {idea.description}
              </p>
            </div>
          )}

          {idea.hooks.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                Hooks
              </p>
              <ul className="space-y-1.5">
                {idea.hooks.map((hook, i) => (
                  <li
                    key={i}
                    className="text-sm text-[var(--color-text-secondary)] flex items-start gap-2"
                  >
                    <span className="text-[var(--color-text-muted)] font-mono text-xs mt-0.5 shrink-0">
                      {i + 1}.
                    </span>
                    {hook}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {idea.key_points.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                Key Points
              </p>
              <ul className="space-y-1.5">
                {idea.key_points.map((point, i) => (
                  <li
                    key={i}
                    className="text-sm text-[var(--color-text-secondary)] flex items-start gap-2"
                  >
                    <Target className="w-3 h-3 text-[var(--color-text-muted)] mt-0.5 shrink-0" />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-3 pt-1 text-[10px] text-[var(--color-text-muted)]">
            {idea.source_type && <span>Source: {idea.source_type}</span>}
            <span>
              {new Date(idea.created_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────── */
export default function ContentIdeasPage() {
  const { getToken } = useAuth();
  const [ideas, setIdeas] = useState<ContentIdea[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("");

  const fetchIdeas = useCallback(async () => {
    try {
      const token = await getToken();
      const params = new URLSearchParams({ limit: "50" });
      if (filterType) params.set("content_type", filterType);
      const res = await fetch(
        `${DIRECT_API_URL}/api/profile/ideas/content?${params}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      );
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      setIdeas(Array.isArray(data) ? data : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load ideas");
    } finally {
      setLoading(false);
    }
  }, [getToken, filterType]);

  useEffect(() => {
    fetchIdeas();
  }, [fetchIdeas]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const token = await getToken();
      const res = await fetch(
        `${DIRECT_API_URL}/api/profile/ideas/content/generate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const newIdeas = await res.json();
      if (Array.isArray(newIdeas) && newIdeas.length > 0) {
        setIdeas((prev) => {
          const existingIds = new Set(prev.map((i) => i.id));
          const fresh = newIdeas.filter(
            (i: ContentIdea) => !existingIds.has(i.id)
          );
          return [...fresh, ...prev];
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate ideas");
    } finally {
      setGenerating(false);
    }
  };

  const contentTypes = Array.from(
    new Set(ideas.map((i) => i.content_type).filter(Boolean) as string[])
  );

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Lightbulb className="w-6 h-6" />
            Content Ideas
          </h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            AI-generated content ideas tailored to your business
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-accent)] text-[var(--color-accent-foreground)] text-sm font-medium rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
        >
          {generating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {generating ? "Generating..." : "Generate Ideas"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Filter bar */}
      {contentTypes.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setFilterType("")}
            className={clsx(
              "px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors",
              filterType === ""
                ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] border-transparent"
                : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
            )}
          >
            All
          </button>
          {contentTypes.map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type === filterType ? "" : type)}
              className={clsx(
                "px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors capitalize",
                filterType === type
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] border-transparent"
                  : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-subtle)]"
              )}
            >
              {type}
            </button>
          ))}
          {ideas.length > 0 && (
            <button
              onClick={fetchIdeas}
              className="ml-auto flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              Refresh
            </button>
          )}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-6 h-6 animate-spin text-[var(--color-text-muted)]" />
            <p className="text-xs text-[var(--color-text-muted)]">
              Loading ideas...
            </p>
          </div>
        </div>
      ) : ideas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-14 h-14 rounded-full bg-[var(--color-surface-muted)] flex items-center justify-center mb-4">
            <FileText className="w-7 h-7 text-[var(--color-text-muted)]" />
          </div>
          <h3 className="text-base font-semibold mb-1">No content ideas yet</h3>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-xs mb-5">
            Generate personalised content ideas based on your business profile
            and goals.
          </p>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-[var(--color-accent-foreground)] text-sm font-medium rounded-lg hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {generating ? "Generating..." : "Generate Ideas"}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-[var(--color-text-muted)]">
            {ideas.length} idea{ideas.length !== 1 ? "s" : ""}
          </p>
          {ideas.map((idea) => (
            <IdeaCard key={idea.id} idea={idea} />
          ))}
        </div>
      )}
    </div>
  );
}