"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { DIRECT_API_URL } from "@/lib/api";
import {
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
import { PageHeader, Card, Button, EmptyState } from "@/app/_components/ui";

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

/* ── Content idea card ─────────────────────────────── */
function IdeaCard({ idea }: { idea: ContentIdea }) {
  const [expanded, setExpanded] = useState(false);

  const priorityColor =
    idea.priority >= 8
      ? "bg-success-soft text-success border-success/20"
      : idea.priority >= 5
        ? "bg-warning-soft text-warning border-warning/20"
        : "bg-surface-muted text-ink-secondary border-line";

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-5 py-4 text-left transition-colors duration-150 hover:bg-surface-muted/40"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              {idea.content_type && (
                <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-ink-secondary">
                  <Tag className="h-2.5 w-2.5" aria-hidden="true" />
                  {idea.content_type}
                </span>
              )}
              <span
                className={clsx(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                  priorityColor
                )}
              >
                <BarChart2 className="h-2.5 w-2.5" aria-hidden="true" />
                Priority {idea.priority}/10
              </span>
            </div>
            <p className="text-sm font-semibold leading-snug text-ink">{idea.title}</p>
            {idea.target_audience && (
              <p className="mt-1 flex items-center gap-1 text-xs text-ink-secondary">
                <Users className="h-3 w-3" aria-hidden="true" />
                {idea.target_audience}
              </p>
            )}
          </div>
          {expanded ? (
            <ChevronUp className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
          ) : (
            <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="space-y-4 border-t border-line-subtle px-5 pb-5">
          {idea.description && (
            <div className="pt-4">
              <p className="mb-1 text-[11px] font-semibold text-ink-secondary">
                Description
              </p>
              <p className="text-sm leading-relaxed text-ink-secondary">
                {idea.description}
              </p>
            </div>
          )}

          {idea.hooks.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold text-ink-secondary">
                Hooks
              </p>
              <ul className="space-y-1.5">
                {idea.hooks.map((hook, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-ink-secondary"
                  >
                    <span className="mt-0.5 shrink-0 font-mono text-xs text-ink-muted">
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
              <p className="mb-2 text-[11px] font-semibold text-ink-secondary">
                Key points
              </p>
              <ul className="space-y-1.5">
                {idea.key_points.map((point, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-ink-secondary"
                  >
                    <Target className="mt-0.5 h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-3 pt-1 text-[10px] text-ink-secondary">
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
    </Card>
  );
}

/* ── Main page ─────────────────────────────────────── */
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
    <div className="max-w-3xl space-y-6">
      <PageHeader
        title="Content ideas"
        description="AI-generated content ideas tailored to your business"
        actions={
          <Button onClick={handleGenerate} loading={generating}>
            {!generating && <Sparkles className="h-4 w-4" aria-hidden="true" />}
            {generating ? "Generating" : "Generate ideas"}
          </Button>
        }
      />

      {/* Error */}
      {error && (
        <div className="rounded-control border border-danger/20 bg-danger-soft p-4 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Filter bar */}
      {contentTypes.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setFilterType("")}
            className={clsx(
              "rounded-control border px-3 py-1.5 text-xs font-medium transition-colors duration-150",
              filterType === ""
                ? "border-transparent bg-accent text-white"
                : "border-line text-ink-secondary hover:bg-surface-muted/60"
            )}
          >
            All
          </button>
          {contentTypes.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilterType(type === filterType ? "" : type)}
              className={clsx(
                "rounded-control border px-3 py-1.5 text-xs font-medium capitalize transition-colors duration-150",
                filterType === type
                  ? "border-transparent bg-accent text-white"
                  : "border-line text-ink-secondary hover:bg-surface-muted/60"
              )}
            >
              {type}
            </button>
          ))}
          {ideas.length > 0 && (
            <button
              type="button"
              onClick={fetchIdeas}
              className="ml-auto flex items-center gap-1.5 text-xs text-ink-secondary transition-colors duration-150 hover:text-ink"
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              Refresh
            </button>
          )}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden="true" />
            <p className="text-xs text-ink-secondary">Loading ideas</p>
          </div>
        </div>
      ) : ideas.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No content ideas yet"
          body="Generate personalised ideas based on your business profile and goals."
          action={
            <Button onClick={handleGenerate} loading={generating}>
              {!generating && <Sparkles className="h-4 w-4" aria-hidden="true" />}
              {generating ? "Generating" : "Generate ideas"}
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-ink-secondary">
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
