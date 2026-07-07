-- ============================================================================
-- FOUNDER OS - DATABASE SCHEMA
-- PostgreSQL 16 + pgvector
-- ============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- CORE TABLES
-- ============================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_user_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    avatar_url TEXT,
    subscription_tier VARCHAR(50) DEFAULT 'free',
    subscription_status VARCHAR(50) DEFAULT 'trial',
    trial_ends_at TIMESTAMP WITH TIME ZONE,
    stripe_customer_id VARCHAR(255),
    monthly_task_limit INTEGER DEFAULT 100,
    monthly_tasks_used INTEGER DEFAULT 0,
    last_reset_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE founder_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    business_name VARCHAR(255),
    business_type VARCHAR(100),
    business_stage VARCHAR(100),
    industry VARCHAR(100),
    target_audience TEXT,
    primary_goal VARCHAR(100),
    current_mrr DECIMAL(10, 2),
    current_users INTEGER,
    monthly_traffic INTEGER,
    working_hours JSONB,
    preferred_communication VARCHAR(50),
    writing_voice TEXT,
    team_size INTEGER DEFAULT 1,
    team_roles JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- AGENT SYSTEM
-- ============================================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    model VARCHAR(100) DEFAULT 'claude-sonnet-4-20250514',
    temperature DECIMAL(3, 2) DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 4000,
    capabilities JSONB,
    available_tools JSONB,
    is_active BOOLEAN DEFAULT true,
    version VARCHAR(20) DEFAULT '1.0',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE user_agent_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    custom_instructions TEXT,
    tone_adjustments TEXT,
    example_outputs JSONB,
    is_enabled BOOLEAN DEFAULT true,
    auto_execute BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, agent_id)
);

-- ============================================================================
-- WORKFLOW SYSTEM
-- ============================================================================

CREATE TABLE workflow_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    category VARCHAR(100),
    steps JSONB NOT NULL,
    trigger_type VARCHAR(50),
    trigger_config JSONB,
    estimated_duration_minutes INTEGER,
    is_public BOOLEAN DEFAULT true,
    is_featured BOOLEAN DEFAULT false,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id UUID REFERENCES workflow_templates(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    steps JSONB NOT NULL,
    is_scheduled BOOLEAN DEFAULT false,
    schedule_cron VARCHAR(100),
    next_run_at TIMESTAMP WITH TIME ZONE,
    last_run_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    total_runs INTEGER DEFAULT 0,
    successful_runs INTEGER DEFAULT 0,
    n8n_workflow_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pending',
    trigger_type VARCHAR(50),
    triggered_by JSONB,
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER NOT NULL,
    steps_completed INTEGER DEFAULT 0,
    steps_failed INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    output_summary TEXT,
    error_message TEXT,
    step_state JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- TASK SYSTEM
-- ============================================================================

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_execution_id UUID REFERENCES workflow_executions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id),
    task_type VARCHAR(100),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    input_data JSONB,
    output_data JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    requires_approval BOOLEAN DEFAULT true,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    approval_notes TEXT,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    tokens_used INTEGER,
    cost_usd DECIMAL(10, 4),
    error_message TEXT,
    error_details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE task_dependencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dependency_type VARCHAR(50) DEFAULT 'blocking',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(task_id, depends_on_task_id)
);

-- ============================================================================
-- CONTEXT & KNOWLEDGE MANAGEMENT
-- ============================================================================

CREATE TABLE knowledge_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    content TEXT NOT NULL,
    content_type VARCHAR(50),
    source_url TEXT,
    category VARCHAR(100),
    tags TEXT[],
    embedding vector(1536),
    file_path TEXT,
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    times_referenced INTEGER DEFAULT 0,
    last_referenced_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    processing_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE context_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    knowledge_item_id UUID NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    relevance_score DECIMAL(5, 4),
    was_useful BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE business_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric_type VARCHAR(100),
    metric_value DECIMAL(15, 2),
    metric_unit VARCHAR(50),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    source VARCHAR(100),
    source_id VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- INTEGRATIONS
-- ============================================================================

CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    integration_type VARCHAR(100),
    display_name VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    config JSONB,
    scopes TEXT[],
    is_active BOOLEAN DEFAULT true,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50),
    sync_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, integration_type)
);

CREATE TABLE integration_syncs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    sync_type VARCHAR(100),
    status VARCHAR(50),
    records_synced INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- OUTPUT MANAGEMENT
-- ============================================================================

CREATE TABLE outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    output_type VARCHAR(100),
    title VARCHAR(500),
    content TEXT,
    format VARCHAR(50),
    word_count INTEGER,
    estimated_read_time_minutes INTEGER,
    publish_status VARCHAR(50) DEFAULT 'draft',
    published_at TIMESTAMP WITH TIME ZONE,
    published_to TEXT[],
    external_urls JSONB,
    version INTEGER DEFAULT 1,
    parent_output_id UUID REFERENCES outputs(id),
    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
    user_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- ANALYTICS & LEARNING
-- ============================================================================

CREATE TABLE agent_analytics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id),
    user_id UUID REFERENCES users(id),
    metric_date DATE NOT NULL,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    average_duration_seconds INTEGER,
    average_tokens_used INTEGER,
    total_cost_usd DECIMAL(10, 4),
    approval_rate DECIMAL(5, 4),
    average_user_rating DECIMAL(3, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(agent_id, user_id, metric_date)
);

CREATE TABLE task_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback_type VARCHAR(50),
    comments TEXT,
    action_taken VARCHAR(50),
    edits_made TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE learning_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id),
    insight_type VARCHAR(100),
    description TEXT,
    pattern_data JSONB,
    occurrences INTEGER DEFAULT 1,
    improvement_action TEXT,
    applied_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- NOTIFICATIONS & COMMUNICATION
-- ============================================================================

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type VARCHAR(100),
    title VARCHAR(255) NOT NULL,
    message TEXT,
    action_url TEXT,
    related_entity_type VARCHAR(50),
    related_entity_id UUID,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    sent_via TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_enabled BOOLEAN DEFAULT true,
    slack_enabled BOOLEAN DEFAULT false,
    push_enabled BOOLEAN DEFAULT true,
    preferences JSONB DEFAULT '{
        "task_completed": true,
        "approval_needed": true,
        "workflow_failed": true,
        "weekly_summary": true,
        "tips_and_insights": false
    }'::jsonb,
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    quiet_hours_timezone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ============================================================================
-- BILLING & USAGE
-- ============================================================================

CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    description TEXT,
    price_monthly_usd DECIMAL(10, 2),
    price_yearly_usd DECIMAL(10, 2),
    monthly_task_limit INTEGER,
    agent_limit INTEGER,
    workflow_limit INTEGER,
    knowledge_items_limit INTEGER,
    team_members_limit INTEGER,
    features JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_type VARCHAR(100),
    quantity INTEGER DEFAULT 1,
    cost_usd DECIMAL(10, 4),
    metadata JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    billing_period_start DATE,
    billing_period_end DATE
);

-- ============================================================================
-- AUDIT & SECURITY
-- ============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    changes JSONB,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    key_prefix VARCHAR(20),
    scopes TEXT[],
    last_used_at TIMESTAMP WITH TIME ZONE,
    usage_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_clerk_id ON users(clerk_user_id);
CREATE INDEX idx_users_subscription_status ON users(subscription_status);

CREATE INDEX idx_tasks_user_id ON tasks(user_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX idx_tasks_workflow_execution_id ON tasks(workflow_execution_id);
CREATE INDEX idx_tasks_agent_id ON tasks(agent_id);

CREATE INDEX idx_workflows_user_id ON workflows(user_id);
CREATE INDEX idx_workflows_next_run_at ON workflows(next_run_at) WHERE is_scheduled = true;

CREATE INDEX idx_workflow_executions_workflow_id ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);
CREATE INDEX idx_workflow_executions_created_at ON workflow_executions(created_at DESC);

CREATE INDEX idx_knowledge_items_user_id ON knowledge_items(user_id);
CREATE INDEX idx_knowledge_items_category ON knowledge_items(category);
CREATE INDEX idx_knowledge_items_tags ON knowledge_items USING GIN(tags);
CREATE INDEX idx_knowledge_items_content_search ON knowledge_items USING gin(to_tsvector('english', content));

-- pgvector index (ivfflat) — rebuild with more lists when data grows
CREATE INDEX knowledge_items_embedding_idx ON knowledge_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_outputs_task_id ON outputs(task_id);
CREATE INDEX idx_outputs_user_id ON outputs(user_id);
CREATE INDEX idx_outputs_type ON outputs(output_type);
CREATE INDEX idx_outputs_status ON outputs(publish_status);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read) WHERE is_read = false;
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);

CREATE INDEX idx_business_metrics_user_id ON business_metrics(user_id);
CREATE INDEX idx_business_metrics_type_date ON business_metrics(metric_type, period_start);

CREATE INDEX idx_integrations_user_id ON integrations(user_id);
CREATE INDEX idx_integrations_type ON integrations(integration_type);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_founder_profiles_updated_at BEFORE UPDATE ON founder_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_workflows_updated_at BEFORE UPDATE ON workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_knowledge_items_updated_at BEFORE UPDATE ON knowledge_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_outputs_updated_at BEFORE UPDATE ON outputs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_integrations_updated_at BEFORE UPDATE ON integrations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

CREATE OR REPLACE VIEW tasks_pending_approval AS
SELECT t.*, a.display_name as agent_name, u.email as user_email
FROM tasks t
JOIN agents a ON t.agent_id = a.id
JOIN users u ON t.user_id = u.id
WHERE t.status = 'awaiting_approval'
AND t.requires_approval = true
ORDER BY t.created_at DESC;

CREATE OR REPLACE VIEW user_dashboard_summary AS
SELECT
    u.id as user_id,
    u.email,
    u.subscription_tier,
    COUNT(DISTINCT t.id) FILTER (WHERE t.created_at > NOW() - INTERVAL '7 days') as tasks_last_7_days,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'awaiting_approval') as tasks_pending_approval,
    COUNT(DISTINCT w.id) as total_workflows,
    COUNT(DISTINCT w.id) FILTER (WHERE w.is_scheduled = true) as scheduled_workflows,
    COUNT(DISTINCT ki.id) as knowledge_items,
    u.monthly_tasks_used,
    u.monthly_task_limit
FROM users u
LEFT JOIN tasks t ON u.id = t.user_id
LEFT JOIN workflows w ON u.id = w.user_id
LEFT JOIN knowledge_items ki ON u.id = ki.user_id
WHERE u.deleted_at IS NULL
GROUP BY u.id;

CREATE OR REPLACE VIEW agent_performance_summary AS
SELECT
    a.id as agent_id,
    a.display_name,
    COUNT(t.id) as total_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'completed') as completed_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'failed') as failed_tasks,
    ROUND(AVG(t.duration_seconds)) as avg_duration_seconds,
    ROUND(AVG(t.tokens_used)) as avg_tokens,
    SUM(t.cost_usd) as total_cost
FROM agents a
LEFT JOIN tasks t ON a.id = t.agent_id
WHERE t.created_at > NOW() - INTERVAL '30 days'
GROUP BY a.id, a.display_name;

-- ============================================================================
-- TABLE COMMENTS
-- ============================================================================

COMMENT ON TABLE users IS 'Core user accounts with subscription info';
COMMENT ON TABLE founder_profiles IS 'Business context and preferences for each founder';
COMMENT ON TABLE agents IS 'AI agent definitions with their capabilities and prompts';
COMMENT ON TABLE workflows IS 'User-created workflows (instances of templates)';
COMMENT ON TABLE workflow_templates IS 'Pre-built workflow templates available to all users';
COMMENT ON TABLE tasks IS 'Individual agent tasks/jobs with execution tracking';
COMMENT ON TABLE knowledge_items IS 'Documents and context for RAG, with vector embeddings';
COMMENT ON TABLE outputs IS 'Content and materials generated by agents';
COMMENT ON TABLE integrations IS 'External tool connections (Stripe, Notion, etc)';

-- ============================================================================
-- SEED DATA
-- ============================================================================

-- Default agents
INSERT INTO agents (name, display_name, description, system_prompt, capabilities, available_tools) VALUES
('planner', 'Planning Agent', 'Analyzes metrics and creates strategic plans',
 'You are a strategic planning expert who helps founders prioritize and plan their work.',
 '["analysis", "prioritization", "planning"]'::jsonb,
 '["metrics_analysis", "task_breakdown"]'::jsonb),
('content', 'Content Agent', 'Creates blog posts, social media content, and marketing materials',
 'You are a marketing expert specializing in founder-led growth and content creation.',
 '["content_creation", "copywriting", "seo"]'::jsonb,
 '["text_generation", "seo_analysis"]'::jsonb),
('research', 'Research Agent', 'Conducts market research and competitive analysis',
 'You are a market research analyst who provides data-driven insights.',
 '["web_search", "data_analysis", "reporting"]'::jsonb,
 '["web_search", "data_scraping", "report_generation"]'::jsonb),
('ops', 'Operations Agent', 'Tracks metrics, generates reports, and manages administrative tasks',
 'You are an operations manager who keeps track of business metrics and generates insights.',
 '["data_analysis", "reporting", "metrics_tracking"]'::jsonb,
 '["analytics_integration", "report_generation"]'::jsonb),
('product', 'Product Agent', 'Manages documentation, changelogs, and product specifications',
 'You are a product manager who maintains clear documentation and product information.',
 '["documentation", "technical_writing", "specification"]'::jsonb,
 '["doc_generation", "changelog_creation"]'::jsonb),
('support', 'Support Agent', 'Handles customer communications and creates support materials',
 'You are a customer support specialist who provides clear, helpful assistance.',
 '["customer_communication", "faq_creation", "troubleshooting"]'::jsonb,
 '["email_drafting", "faq_generation", "doc_search"]'::jsonb),
('orchestrator', 'Orchestrator', 'Chief-of-staff agent that understands the big picture, routes tasks to specialist agents, synthesises their outputs, and conveys results to the user',
 'You are the chief-of-staff orchestrator for Founder OS. You understand the full picture, break complex requests into sub-tasks, delegate to specialist agents, and synthesise their outputs into a coherent response.',
 '["orchestration", "delegation", "synthesis", "planning", "routing"]'::jsonb,
 '["delegate_task", "get_current_datetime", "get_user_profile", "ask_user_clarification", "store_working_memory", "search_knowledge", "recall_last_orchestration", "list_available_agents", "check_delegation_health"]'::jsonb);

-- Default workflow templates
INSERT INTO workflow_templates (name, slug, description, category, steps, trigger_type, estimated_duration_minutes) VALUES
('Weekly Planning', 'weekly-planning',
 'Full weekly planning workflow: review last week, scan the market, generate a prioritised plan, schedule content, and create actionable tasks.',
 'planning',
 '[
    {
      "step_number": 1,
      "agent_name": "ops",
      "title": "Compile Last Week Metrics",
      "task_template": "Pull all business metrics for the past 7 days. Summarise: MRR change, active users, traffic, conversion rate, support ticket volume, and any anomalies. Use the get_business_metrics tool. Output a structured dashboard summary.",
      "depends_on": [],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "last_week_metrics",
      "tools_required": ["get_business_metrics", "get_current_datetime"]
    },
    {
      "step_number": 2,
      "agent_name": "planner",
      "title": "Review Prior Week Plan",
      "task_template": "Retrieve the previous weeks plan from shared memory (key: current_plan). For each task that was planned: mark it as completed, partially done, or missed. Calculate the completion rate. Identify any recurring blockers. Output a structured review with a carryover_tasks list of items that need to roll into the new week.",
      "depends_on": [],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "prior_week_review",
      "tools_required": ["list_tasks", "get_current_datetime", "store_working_memory"]
    },
    {
      "step_number": 3,
      "agent_name": "research",
      "title": "Market & Competitor Scan",
      "task_template": "Given the founders industry (from context), run a quick scan for: (1) competitor moves in the last 7 days, (2) relevant market/industry news, (3) trending topics in the founders space. Use web_search. Summarise the top 5 actionable insights. Reference: {{last_week_metrics}}",
      "depends_on": [1],
      "requires_approval": false,
      "timeout_seconds": 180,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "market_scan",
      "tools_required": ["web_search", "search_knowledge"]
    },
    {
      "step_number": 4,
      "agent_name": "planner",
      "title": "Generate Weekly Plan",
      "task_template": "Using the following inputs, create a prioritised weekly plan:\n\n1. Last Week Metrics: {{last_week_metrics}}\n2. Prior Plan Review: {{prior_week_review}} (include carryover tasks)\n3. Market Intelligence: {{market_scan}}\n4. Founder Profile: {{founder_profile}}\n\nOutput format:\n- Top 3 Priorities for the week (with rationale)\n- Daily breakdown (Mon-Fri) with specific tasks, owners (which agent), and time estimates\n- Delegations: list of tasks to delegate to content/research/ops/product/support agents\n- Risks and mitigations\n- Success criteria for the week\n\nSave the plan to shared memory under key current_plan.",
      "depends_on": [1, 2, 3],
      "requires_approval": true,
      "timeout_seconds": 300,
      "retry_on_failure": true,
      "max_retries": 1,
      "output_key": "weekly_plan",
      "tools_required": ["create_task", "store_working_memory", "get_current_datetime", "search_knowledge"]
    },
    {
      "step_number": 5,
      "agent_name": "content",
      "title": "Schedule Content Calendar",
      "task_template": "Based on the weekly plan ({{weekly_plan}}), create a content calendar for the week:\n- Blog posts / articles to write (with topics + target publish day)\n- Social media posts (LinkedIn, Twitter/X) - 1 per day minimum\n- Newsletter if scheduled\n- Any launch announcements\n\nMatch the founders writing voice (use get_writing_style). Save each piece as a draft via save_draft.",
      "depends_on": [4],
      "requires_approval": true,
      "timeout_seconds": 240,
      "retry_on_failure": true,
      "max_retries": 1,
      "output_key": "content_calendar",
      "tools_required": ["save_draft", "get_writing_style", "get_current_datetime"]
    },
    {
      "step_number": 6,
      "agent_name": "ops",
      "title": "Create Tasks & Send Notifications",
      "task_template": "Take the approved weekly plan ({{weekly_plan}}) and:\n1. Create individual task records for each item using create_task\n2. Set priorities (1=urgent, 10=backlog)\n3. Assign each task to the appropriate agent\n4. Generate a summary notification for the founder with the weeks key objectives\n\nOutput: list of created task IDs and the notification content.",
      "depends_on": [4],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "task_creation_summary",
      "tools_required": ["create_task", "list_tasks", "get_current_datetime"]
    }
 ]'::jsonb,
 'scheduled', 15),
('Content Creation', 'content-creation', 'Research and create blog content', 'marketing',
 '[
    {"step_number": 1, "agent_name": "research", "task_template": "Research topic and gather insights", "requires_approval": false},
    {"step_number": 2, "agent_name": "content", "task_template": "Write blog post draft", "requires_approval": true},
    {"step_number": 3, "agent_name": "content", "task_template": "Create social media posts", "requires_approval": true}
 ]'::jsonb,
 'manual', 20),
('Product Launch', 'product-launch', 'Complete product launch workflow', 'product',
 '[
    {"step_number": 1, "agent_name": "product", "task_template": "Update changelog and documentation", "requires_approval": true},
    {"step_number": 2, "agent_name": "content", "task_template": "Write launch announcement", "requires_approval": true},
    {"step_number": 3, "agent_name": "support", "task_template": "Prepare customer FAQs", "requires_approval": true},
    {"step_number": 4, "agent_name": "ops", "task_template": "Setup tracking metrics", "requires_approval": false}
 ]'::jsonb,
 'manual', 30),
('Customer Onboarding', 'customer-onboarding', 'Automate new customer onboarding flow', 'operations',
 '[
    {"step_number": 1, "agent_name": "support", "task_template": "Generate personalized welcome email", "requires_approval": true},
    {"step_number": 2, "agent_name": "product", "task_template": "Create onboarding checklist", "requires_approval": false},
    {"step_number": 3, "agent_name": "ops", "task_template": "Setup tracking for new customer", "requires_approval": false}
 ]'::jsonb,
 'event', 10);

-- Subscription plans
INSERT INTO subscription_plans (name, display_name, description, price_monthly_usd, price_yearly_usd,
                                monthly_task_limit, agent_limit, workflow_limit, knowledge_items_limit, team_members_limit, features) VALUES
('free', 'Free Trial', '14-day trial with limited features', 0, 0, 50, 3, 2, 10, 1,
 '["basic_agents", "manual_workflows"]'::jsonb),
('starter', 'Starter', 'For solo founders getting started', 99, 999, 500, 5, 10, 100, 1,
 '["all_agents", "scheduled_workflows", "basic_integrations", "email_support"]'::jsonb),
('pro', 'Pro', 'For growing teams', 299, 2999, 2000, 10, 50, 500, 5,
 '["all_agents", "custom_workflows", "advanced_integrations", "priority_support", "api_access"]'::jsonb),
('enterprise', 'Enterprise', 'Custom solution for larger teams', 999, 9999, 999999, 999, 999, 9999, 50,
 '["all_agents", "custom_workflows", "all_integrations", "dedicated_support", "api_access", "white_label", "sla"]'::jsonb);


-- ============================================================================
-- AGENT EVOLUTION ENGINE (task 003)
-- ============================================================================

-- Structured, versioned model of the founder's business (distilled from
-- founder_profiles + user_profiles_intel) that drives agent regeneration.
CREATE TABLE IF NOT EXISTS founder_context_models (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version      INTEGER NOT NULL DEFAULT 1,
    model        JSONB NOT NULL,
    source_hash  VARCHAR(64) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_founder_context_models_user ON founder_context_models(user_id);

-- Versioned, per-founder regeneration of an agent's full definition. Staged as
-- 'proposed'; founder approval makes it 'active'; the registry prefers the active
-- row over the global agents row.
CREATE TABLE IF NOT EXISTS agent_definitions (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_name             VARCHAR(100) NOT NULL,
    version                INTEGER NOT NULL DEFAULT 1,
    system_prompt          TEXT NOT NULL,
    decision_framework     TEXT,
    selected_tools         JSONB,
    status                 VARCHAR(20) NOT NULL DEFAULT 'proposed',  -- proposed|active|superseded
    context_model_version  INTEGER,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at            TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_agent_definitions_user ON agent_definitions(user_id);
CREATE INDEX IF NOT EXISTS ix_agent_definitions_user_agent_status
    ON agent_definitions(user_id, agent_name, status);

-- ============================================================================
-- COMPANY STATE ENGINE (ADR-009 slice 1) — secondary sync artifact.
-- Authoritative source: alembic/versions/0002_state_engine.py (CLAUDE.md §5.8).
-- ============================================================================

CREATE TABLE IF NOT EXISTS state_sources (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type             VARCHAR(50) NOT NULL CHECK (type IN ('obsidian','github','stripe','slack','calendar','notion','user_doc','system')),
    name             VARCHAR(255) NOT NULL,
    config           JSONB NOT NULL DEFAULT '{}',
    sync_cursor      JSONB,
    status           VARCHAR(50) NOT NULL DEFAULT 'active',
    last_synced_at   TIMESTAMPTZ,
    last_error       TEXT,
    last_sync_report JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, type, name)
);
CREATE INDEX IF NOT EXISTS ix_state_sources_user ON state_sources(user_id);

CREATE TABLE IF NOT EXISTS company_state_entities (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_type      VARCHAR(50) NOT NULL CHECK (entity_type IN ('goal','project','task','decision','metric','person','meeting','note')),
    title            TEXT NOT NULL,
    status           VARCHAR(50) NOT NULL DEFAULT 'active',
    summary          TEXT,
    attributes       JSONB NOT NULL DEFAULT '{}',
    source           VARCHAR(20) NOT NULL CHECK (source IN ('observed','user_doc','system')),
    source_id        UUID REFERENCES state_sources(id) ON DELETE SET NULL,
    external_ref     VARCHAR(512),
    confidence       NUMERIC(4,3) NOT NULL DEFAULT 0.700,
    last_asserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pinned           BOOLEAN NOT NULL DEFAULT FALSE,
    embedding        vector(1536),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_state_entities_user_type ON company_state_entities(user_id, entity_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_state_entities_user_src_ref
    ON company_state_entities(user_id, source_id, external_ref) WHERE external_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS state_observations (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id    UUID NOT NULL REFERENCES state_sources(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    external_id  VARCHAR(512) NOT NULL,
    kind         VARCHAR(100) NOT NULL,
    payload      JSONB NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    provenance   VARCHAR(20) NOT NULL DEFAULT 'observed' CHECK (provenance IN ('observed','user_doc','system')),
    observed_at  TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    outcome      VARCHAR(50),
    entity_id    UUID REFERENCES company_state_entities(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_state_obs_dedup UNIQUE (source_id, external_id, content_hash)
);
CREATE INDEX IF NOT EXISTS ix_state_obs_lookup ON state_observations(source_id, external_id, observed_at);
CREATE INDEX IF NOT EXISTS ix_state_obs_user ON state_observations(user_id);

CREATE TABLE IF NOT EXISTS state_relations (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_entity_id UUID NOT NULL REFERENCES company_state_entities(id) ON DELETE CASCADE,
    target_entity_id UUID NOT NULL REFERENCES company_state_entities(id) ON DELETE CASCADE,
    relation_type    VARCHAR(50) NOT NULL DEFAULT 'mentions',
    strength         NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    metadata_        JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_entity_id, target_entity_id, relation_type)
);
CREATE INDEX IF NOT EXISTS ix_state_relations_user ON state_relations(user_id);
