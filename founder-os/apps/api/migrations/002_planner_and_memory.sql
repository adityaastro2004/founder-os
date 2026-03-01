-- ============================================================================
-- Founder OS — Migration 002: Persistent Planner + Temporal Memory System
-- ============================================================================
-- Adds:
--   1. planner_users — persistent user profiles & GCal tokens
--   2. plan_history  — historical plan records
--   3. memory_pages  — temporal knowledge graph with decay & review scheduling
--
-- Run:  psql -U founder -d founder_os -f migrations/002_planner_and_memory.sql
-- ============================================================================

-- Ensure pgvector extension exists
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. PLANNER USERS — persistent profiles & tokens
-- ============================================================================

CREATE TABLE IF NOT EXISTS planner_users (
    user_id         VARCHAR(100) PRIMARY KEY,
    name            VARCHAR(255) DEFAULT '',

    -- Business context
    business_name   VARCHAR(255) DEFAULT '',
    business_type   VARCHAR(100) DEFAULT '',
    business_stage  VARCHAR(100) DEFAULT '',
    industry        VARCHAR(100) DEFAULT '',
    target_audience TEXT DEFAULT '',
    team_size       INTEGER DEFAULT 1,

    -- Metrics
    current_mrr     NUMERIC(12,2) DEFAULT 0,
    current_users   INTEGER DEFAULT 0,
    mrr_growth_pct  NUMERIC(5,2) DEFAULT 0,

    -- Weekly planning
    primary_goal    TEXT DEFAULT '',
    goals_this_week JSONB DEFAULT '[]'::jsonb,
    completed_last_week JSONB DEFAULT '[]'::jsonb,
    blockers        JSONB DEFAULT '[]'::jsonb,
    custom_instructions TEXT DEFAULT '',

    -- Preferences
    timezone            VARCHAR(50) DEFAULT 'Asia/Kolkata',
    preferred_work_hours VARCHAR(20) DEFAULT '09:00-18:00',
    calendar_id         VARCHAR(255) DEFAULT 'primary',

    -- Google Calendar OAuth (tokens stored securely)
    gcal_connected      BOOLEAN DEFAULT FALSE,
    gcal_access_token   TEXT,
    gcal_refresh_token  TEXT,
    gcal_token_expiry   TIMESTAMP WITH TIME ZONE,
    gcal_token_data     JSONB DEFAULT '{}'::jsonb,

    -- Stats
    plan_count          INTEGER DEFAULT 0,
    last_plan_at        TIMESTAMP WITH TIME ZONE,
    last_plan_events    INTEGER DEFAULT 0,

    -- Timestamps
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planner_users_gcal
    ON planner_users(gcal_connected) WHERE gcal_connected = TRUE;

-- ============================================================================
-- 2. PLAN HISTORY — persistent plan records
-- ============================================================================

CREATE TABLE IF NOT EXISTS plan_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(100) REFERENCES planner_users(user_id) ON DELETE CASCADE,

    plan_id         VARCHAR(50),
    week_of         DATE,
    generated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    task_count      INTEGER DEFAULT 0,
    events_created  INTEGER DEFAULT 0,
    events_failed   INTEGER DEFAULT 0,
    duration_seconds NUMERIC(6,1),

    top_priorities  JSONB DEFAULT '[]'::jsonb,
    plan_data       JSONB DEFAULT '{}'::jsonb,
    gcal_events     JSONB DEFAULT '[]'::jsonb,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plan_history_user
    ON plan_history(user_id, generated_at DESC);

-- ============================================================================
-- 3. MEMORY PAGES — Temporal Knowledge Graph
-- ============================================================================
-- This replaces pure vector similarity with a page-indexed, temporally-aware
-- memory system. Each "page" is a discrete memory unit with:
--   - Temporal metadata (when it happened, created, last accessed)
--   - Importance scoring with configurable decay rates
--   - Review scheduling (spaced repetition for business items)
--   - Chapter-based organisation (product, hiring, funding, marketing, etc.)
--   - Entity linking (people, companies, tools referenced)
--   - Embedding for optional hybrid search
--
-- Retrieval uses composite scoring:
--   score = (semantic_sim * w1) + (temporal_relevance * w2) + (importance * w3) + (access_freq * w4)
--
-- Where temporal_relevance = importance * exp(-decay_rate * days_since)
-- ============================================================================

CREATE TABLE IF NOT EXISTS memory_pages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(100) NOT NULL,

    -- Classification
    page_type       VARCHAR(50) NOT NULL DEFAULT 'event',
        -- Types: event, decision, milestone, insight, metric, interaction,
        --        goal, blocker, feedback, plan_outcome, learning

    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT,           -- Short summary for quick retrieval / LLM context

    -- ── Temporal Metadata ──
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,  -- When this actually happened
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count    INTEGER DEFAULT 0,

    -- ── Importance & Decay ──
    importance      NUMERIC(4,3) DEFAULT 0.500,    -- 0.000 to 1.000
    decay_rate      NUMERIC(6,5) DEFAULT 0.00100,  -- Lower = slower decay
    is_pinned       BOOLEAN DEFAULT FALSE,          -- Pinned items never decay

    -- ── Review Scheduling (spaced repetition) ──
    next_review_at      TIMESTAMP WITH TIME ZONE,  -- When to resurface
    review_interval_days INTEGER,                   -- e.g., 7, 30, 90, 180
    review_count        INTEGER DEFAULT 0,
    last_reviewed_at    TIMESTAMP WITH TIME ZONE,

    -- ── Organisation ──
    chapter         VARCHAR(100),      -- Logical grouping: product, hiring, funding, marketing, ops, growth, support
    tags            TEXT[] DEFAULT '{}',
    entities        JSONB DEFAULT '{}', -- {"people": [...], "companies": [...], "tools": [...], "metrics": {...}}

    -- ── Relations ──
    parent_id       UUID REFERENCES memory_pages(id) ON DELETE SET NULL,
    related_ids     UUID[] DEFAULT '{}',

    -- ── Embedding (optional, for hybrid search) ──
    embedding       vector(1536),

    -- ── Source & Metadata ──
    source          VARCHAR(100) DEFAULT 'user_input',
        -- Sources: user_input, planner, calendar, metric_update, agent, system, import
    metadata_       JSONB DEFAULT '{}'::jsonb,

    -- ── Soft delete ──
    is_active       BOOLEAN DEFAULT TRUE
);

-- Temporal queries: "what happened recently?"
CREATE INDEX IF NOT EXISTS idx_memory_user_occurred
    ON memory_pages(user_id, occurred_at DESC)
    WHERE is_active = TRUE;

-- Chapter browsing: "show me all hiring memories"
CREATE INDEX IF NOT EXISTS idx_memory_user_chapter
    ON memory_pages(user_id, chapter, occurred_at DESC)
    WHERE is_active = TRUE;

-- Review surfacing: "what needs attention today?"
CREATE INDEX IF NOT EXISTS idx_memory_review_due
    ON memory_pages(next_review_at)
    WHERE next_review_at IS NOT NULL AND is_active = TRUE;

-- Importance ranking: "what are the most important things?"
CREATE INDEX IF NOT EXISTS idx_memory_importance
    ON memory_pages(user_id, importance DESC)
    WHERE is_active = TRUE;

-- Type filtering: "all decisions", "all milestones"
CREATE INDEX IF NOT EXISTS idx_memory_user_type
    ON memory_pages(user_id, page_type, occurred_at DESC)
    WHERE is_active = TRUE;

-- Vector similarity (for optional hybrid search)
-- Using ivfflat — rebuild with more lists as data grows
CREATE INDEX IF NOT EXISTS idx_memory_embedding
    ON memory_pages USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 20);

-- Full-text search on content
CREATE INDEX IF NOT EXISTS idx_memory_content_fts
    ON memory_pages USING gin(to_tsvector('english', content));

-- Tag search
CREATE INDEX IF NOT EXISTS idx_memory_tags
    ON memory_pages USING gin(tags);

-- Entity search (JSONB)
CREATE INDEX IF NOT EXISTS idx_memory_entities
    ON memory_pages USING gin(entities jsonb_path_ops);

-- ============================================================================
-- 4. MEMORY LINKS — explicit relationships between memories
-- ============================================================================

CREATE TABLE IF NOT EXISTS memory_links (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id   UUID NOT NULL REFERENCES memory_pages(id) ON DELETE CASCADE,
    target_id   UUID NOT NULL REFERENCES memory_pages(id) ON DELETE CASCADE,
    link_type   VARCHAR(50) NOT NULL DEFAULT 'related',
        -- Types: related, caused_by, led_to, contradicts, updates, supersedes, part_of
    strength    NUMERIC(3,2) DEFAULT 0.50,  -- 0.00 to 1.00
    metadata_   JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(source_id, target_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_memory_links_source
    ON memory_links(source_id);
CREATE INDEX IF NOT EXISTS idx_memory_links_target
    ON memory_links(target_id);

-- ============================================================================
-- 5. Utility function: temporal relevance scoring
-- ============================================================================

CREATE OR REPLACE FUNCTION memory_temporal_score(
    p_importance NUMERIC,
    p_decay_rate NUMERIC,
    p_occurred_at TIMESTAMP WITH TIME ZONE,
    p_is_pinned BOOLEAN DEFAULT FALSE
) RETURNS NUMERIC AS $$
BEGIN
    IF p_is_pinned THEN
        RETURN p_importance;
    END IF;
    -- Exponential decay: importance * exp(-decay_rate * days_since)
    RETURN p_importance * EXP(
        -p_decay_rate * GREATEST(
            EXTRACT(EPOCH FROM (NOW() - p_occurred_at)) / 86400.0,
            0
        )
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- Done
-- ============================================================================

