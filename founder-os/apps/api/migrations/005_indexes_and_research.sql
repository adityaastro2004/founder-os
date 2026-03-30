-- Migration 005: Performance indexes + Research crawler tables
-- ============================================================

-- ── Performance indexes for hot query paths ──

-- Chat messages: session history loading (agent_routes._load_session_history)
CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages (user_id, session_id, agent_name, created_at DESC);

-- Agent runs: listing by user/session
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_session
    ON agent_runs (user_id, session_id, created_at DESC);

-- Memory pages: user_id + occurred_at (recall queries)
CREATE INDEX IF NOT EXISTS idx_memory_pages_user_occurred
    ON memory_pages (user_id, occurred_at DESC)
    WHERE is_active = TRUE;

-- Memory pages: chapter browsing
CREATE INDEX IF NOT EXISTS idx_memory_pages_user_chapter
    ON memory_pages (user_id, chapter, occurred_at DESC)
    WHERE is_active = TRUE AND chapter IS NOT NULL;

-- Memory pages: review scheduling
CREATE INDEX IF NOT EXISTS idx_memory_pages_review_due
    ON memory_pages (user_id, next_review_at)
    WHERE next_review_at IS NOT NULL AND is_active = TRUE;

-- Knowledge items: processing status
CREATE INDEX IF NOT EXISTS idx_knowledge_items_processing
    ON knowledge_items (processing_status)
    WHERE processing_status != 'completed';

-- Knowledge items: category + active
CREATE INDEX IF NOT EXISTS idx_knowledge_items_category
    ON knowledge_items (user_id, category)
    WHERE is_active = TRUE;

-- Tasks: user + status
CREATE INDEX IF NOT EXISTS idx_tasks_user_status
    ON tasks (user_id, status, created_at DESC);


-- ── Research crawler tables ──

CREATE TABLE IF NOT EXISTS research_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         VARCHAR(255) NOT NULL,

    -- Run metadata
    status          VARCHAR(50)  NOT NULL DEFAULT 'running',  -- running, completed, failed
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_seconds NUMERIC(8,1),

    -- Stats
    queries_executed   INTEGER NOT NULL DEFAULT 0,
    pages_crawled      INTEGER NOT NULL DEFAULT 0,
    findings_stored    INTEGER NOT NULL DEFAULT 0,

    -- Results summary
    competitor_updates JSONB NOT NULL DEFAULT '[]',
    trends             JSONB NOT NULL DEFAULT '[]',
    customer_signals   JSONB NOT NULL DEFAULT '[]',
    error_message      TEXT,

    -- Research profile snapshot
    profile_snapshot   JSONB NOT NULL DEFAULT '{}',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_runs_user
    ON research_runs (user_id, started_at DESC);

-- Tracked competitors per user
CREATE TABLE IF NOT EXISTS tracked_competitors (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     VARCHAR(255) NOT NULL,
    name        VARCHAR(255) NOT NULL,
    website     VARCHAR(500),
    notes       TEXT DEFAULT '',
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_tracked_competitors_user
    ON tracked_competitors (user_id);

-- Custom research sources per user
CREATE TABLE IF NOT EXISTS research_sources (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     VARCHAR(255) NOT NULL,
    name        VARCHAR(255) NOT NULL,
    url         VARCHAR(1000) NOT NULL,
    source_type VARCHAR(50) NOT NULL DEFAULT 'rss',  -- rss, website, api
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, url)
);

CREATE INDEX IF NOT EXISTS idx_research_sources_user
    ON research_sources (user_id)
    WHERE is_active = TRUE;
