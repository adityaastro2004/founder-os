-- ============================================================================
-- MIGRATION 004: User Intelligence & Business Insights
-- ============================================================================
-- Deep user profiling from all agent interactions.
-- Cross-user pattern detection for business improvement.
-- Content idea generation from aggregated insights.
-- ============================================================================

-- 1. Per-user deep intelligence profile
CREATE TABLE IF NOT EXISTS user_profiles_intel (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,

    -- Personality & communication
    preferred_tone       TEXT,          -- e.g. "casual, direct, no fluff"
    communication_style  TEXT,          -- e.g. "prefers bullet points, asks follow-ups"
    language_patterns    JSONB,         -- recurring phrases, vocabulary level, etc.

    -- Preferences
    likes                JSONB DEFAULT '[]'::jsonb,   -- ["quick responses", "data-driven", ...]
    dislikes             JSONB DEFAULT '[]'::jsonb,   -- ["long intros", "generic advice", ...]
    topics_of_interest   JSONB DEFAULT '[]'::jsonb,   -- ["AI agents", "SaaS pricing", ...]

    -- Pain points & expectations
    pain_points          JSONB DEFAULT '[]'::jsonb,   -- ["scaling team", "content consistency", ...]
    expectations         JSONB DEFAULT '[]'::jsonb,   -- ["fast turnaround", "high quality first draft", ...]
    goals                JSONB DEFAULT '[]'::jsonb,   -- ["reach 10k MRR", "launch by Q2", ...]

    -- Workflow preferences
    preferred_agents     JSONB DEFAULT '[]'::jsonb,   -- ["content", "research"] — most used
    preferred_workflows  JSONB DEFAULT '[]'::jsonb,   -- ["blog→social", "research→content"]
    work_patterns        JSONB,                        -- peak hours, frequency, session length

    -- Interaction quality signals
    satisfaction_score   NUMERIC(3, 2),                -- running avg 1-5
    total_interactions   INTEGER DEFAULT 0,
    positive_signals     INTEGER DEFAULT 0,            -- "thanks", "perfect", re-use, etc.
    negative_signals     INTEGER DEFAULT 0,            -- "no", "wrong", rephrasing, etc.

    -- Aggregated summary (LLM-generated, updated periodically)
    profile_summary      TEXT,                         -- natural language user summary
    conversation_guide   TEXT,                         -- instructions for agents on how to talk to this user

    -- Versioning
    version              INTEGER DEFAULT 1,
    last_analysis_at     TIMESTAMP WITH TIME ZONE,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_user_profiles_intel_user UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_intel_user ON user_profiles_intel(user_id);

-- 2. Individual insights extracted from each interaction
CREATE TABLE IF NOT EXISTS user_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,

    -- Source
    agent_name       VARCHAR(100) NOT NULL,
    session_id       VARCHAR(255),
    agent_run_id     UUID,                            -- FK to agent_runs if available
    source_message   TEXT,                            -- the user message that triggered this insight

    -- Insight data
    insight_type     VARCHAR(50) NOT NULL,            -- 'like', 'dislike', 'pain_point', 'goal',
                                                      -- 'expectation', 'preference', 'feedback',
                                                      -- 'tone_signal', 'topic_interest', 'idea'
    insight_value    TEXT NOT NULL,                   -- the actual insight
    confidence       NUMERIC(3, 2) DEFAULT 0.80,     -- 0.0-1.0 how confident the extraction is
    sentiment        VARCHAR(20),                     -- 'positive', 'negative', 'neutral'

    -- Processing
    is_processed     BOOLEAN DEFAULT FALSE,           -- has been rolled into user_profiles_intel
    processed_at     TIMESTAMP WITH TIME ZONE,

    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_insights_user ON user_insights(user_id);
CREATE INDEX IF NOT EXISTS idx_user_insights_type ON user_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_user_insights_unprocessed ON user_insights(user_id, is_processed) WHERE NOT is_processed;
CREATE INDEX IF NOT EXISTS idx_user_insights_created ON user_insights(created_at DESC);

-- 3. Cross-user business intelligence (patterns across all users)
CREATE TABLE IF NOT EXISTS business_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Pattern data
    insight_type     VARCHAR(100) NOT NULL,           -- 'common_pain_point', 'trending_topic',
                                                      -- 'popular_request', 'content_opportunity',
                                                      -- 'workflow_optimization', 'feature_request',
                                                      -- 'satisfaction_driver', 'churn_risk'
    title            VARCHAR(500) NOT NULL,
    description      TEXT NOT NULL,
    evidence         JSONB DEFAULT '[]'::jsonb,       -- list of supporting user_insight IDs or quotes
    user_count       INTEGER DEFAULT 1,               -- how many users exhibit this pattern
    frequency        INTEGER DEFAULT 1,               -- total occurrences across all users
    impact_score     NUMERIC(3, 2) DEFAULT 0.50,      -- 0-1 estimated business impact

    -- Actionability
    recommended_actions JSONB DEFAULT '[]'::jsonb,    -- suggested actions to take
    status           VARCHAR(50) DEFAULT 'new',       -- 'new', 'reviewed', 'actioned', 'dismissed'
    actioned_at      TIMESTAMP WITH TIME ZONE,

    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_business_insights_type ON business_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_business_insights_impact ON business_insights(impact_score DESC);

-- 4. Content ideas generated from insights
CREATE TABLE IF NOT EXISTS content_ideas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255),                            -- NULL = company-wide idea

    -- Idea data
    title            VARCHAR(500) NOT NULL,
    description      TEXT NOT NULL,
    content_type     VARCHAR(100),                   -- 'blog', 'instagram', 'youtube', 'newsletter', 'thread'
    target_audience  TEXT,
    hooks            JSONB DEFAULT '[]'::jsonb,      -- suggested hooks
    key_points       JSONB DEFAULT '[]'::jsonb,      -- main talking points

    -- Source
    source_type      VARCHAR(50) NOT NULL,           -- 'user_pain_point', 'trending_topic',
                                                      -- 'popular_question', 'success_story',
                                                      -- 'common_objection', 'industry_trend'
    source_insights  JSONB DEFAULT '[]'::jsonb,      -- insight IDs that inspired this idea
    business_insight_id UUID,                         -- if generated from a business_insight

    -- Status
    priority         INTEGER DEFAULT 5,              -- 1-10, higher = more important
    status           VARCHAR(50) DEFAULT 'idea',     -- 'idea', 'planned', 'in_progress', 'published', 'dismissed'

    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_ideas_user ON content_ideas(user_id);
CREATE INDEX IF NOT EXISTS idx_content_ideas_status ON content_ideas(status);
CREATE INDEX IF NOT EXISTS idx_content_ideas_priority ON content_ideas(priority DESC);
