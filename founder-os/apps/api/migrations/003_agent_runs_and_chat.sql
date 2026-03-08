-- Migration 003: Agent Runs & Chat Message Persistence
-- Adds tables for storing agent interaction history and persistent chat messages.

-- ============================================================================
-- AGENT RUNS — stores every agent interaction with full I/O details
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    session_id VARCHAR(255),

    user_message TEXT NOT NULL,
    agent_response TEXT NOT NULL,

    model VARCHAR(100),
    tokens_used INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 6),
    duration_seconds DECIMAL(10, 2),
    stop_reason VARCHAR(50),

    tool_names JSONB,
    tool_calls_count INTEGER DEFAULT 0,

    -- orchestrator-specific
    agents_used JSONB,
    delegations_made INTEGER DEFAULT 0,
    delegation_details JSONB,

    status VARCHAR(50) DEFAULT 'completed',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_agent ON agent_runs(user_id, agent_name, created_at DESC);

-- ============================================================================
-- CHAT MESSAGES — persistent chat messages for agent & orchestrator chats
-- ============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,

    role VARCHAR(20) NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,

    -- metadata for assistant messages
    model VARCHAR(100),
    tokens_used INTEGER,
    duration_seconds DECIMAL(10, 2),
    tool_names JSONB,
    agents_used JSONB,
    delegations_made INTEGER,
    status VARCHAR(50) DEFAULT 'completed',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_agent_name ON chat_messages(agent_name);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_session ON chat_messages(user_id, session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_agent ON chat_messages(user_id, agent_name, created_at DESC);
