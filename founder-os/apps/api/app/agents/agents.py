"""
Founder OS — Concrete Agents (v2)
===================================
Enhanced agents with A2A delegation awareness and capability declarations.

Each agent: planner, content, research, ops, product, support

New in v2:
  - ``capabilities`` lists for A2A routing
  - ``tags`` for keyword-based routing
  - Delegation awareness in system prompts
  - Shared memory for inter-agent context passing
"""

from __future__ import annotations

from app.agents.base import BaseAgent, AgentResult

# Ensure built-in tools are registered on import
import app.agents.builtin_tools  # noqa: F401

# Import MCP calendar tool names so agents can reference them
from app.agents.mcp_tools import CALENDAR_TOOL_NAMES  # noqa: F401


# ============================================================================
# Planner Agent — orchestrates and delegates
# ============================================================================

class PlannerAgent(BaseAgent):
    name = "planner"
    capabilities = [
        "planning", "task_management", "prioritization",
        "delegation", "strategy", "weekly_planning", "goal_setting",
    ]
    tags = [
        "plan", "prioritize", "roadmap", "strategy", "goals",
        "okr", "weekly", "schedule", "focus", "review",
    ]
    default_tools = [
        "search_knowledge",
        "get_business_metrics",
        "get_user_profile",
        "check_calendar_conflicts",
        "ask_user_clarification",
        "detect_calendar_intent",
        "validate_event_fields",
        "create_task",
        "list_tasks",
        "update_task_status",
        "get_current_datetime",
        "store_working_memory",
        # Google Calendar tools (via MCP provider)
        "gcal_list_events",
        "gcal_create_event",
        "gcal_create_all_day_event",
        "gcal_update_event",
        "gcal_delete_event",
        "gcal_get_event",
        "gcal_push_weekly_plan",
        "gcal_smart_delete",
    ]
    default_system_prompt = """\
You are the **Planning Agent** for Founder OS — a weekly-planning specialist \
that helps solo founders and small startup teams make the most of their time.

═══════════════════════════════════════════════════════════════════
MISSION
═══════════════════════════════════════════════════════════════════
Turn raw context (metrics, market intel, prior-week review, founder goals) \
into a crisp, actionable weekly plan that the founder can approve and execute.

═══════════════════════════════════════════════════════════════════
🧠 INTELLIGENCE RULES — THINK BEFORE ACTING
═══════════════════════════════════════════════════════════════════
You are an INTELLIGENT agent — never blindly execute. Follow this protocol:

0. **INTENT DETECTION** — for EVERY calendar-related user message:
   • Call `detect_calendar_intent` FIRST with the user's raw message
   • It returns: intent type, extracted fields, and missing fields
   • If `needs_clarification` is true → ask the user for the missing fields
     BEFORE doing anything. Example:
       User: "Schedule a meeting tomorrow"
       → detect_calendar_intent says: intent=create, missing=[start_time, duration, title]
       → You reply: "I can schedule that! A few details I need:
         - What time should it start?
         - How long is the meeting? (30 min, 1 hour, etc.)
         - What should I call it?"
   • Only proceed with the calendar action once ALL required fields are present

1. **GATHER CONTEXT FIRST** — before ANY calendar operation or plan, call:
   • `get_user_profile` — to know the founder's primary goal, business stage,
     blockers, preferred work hours, and timezone
   • `gcal_list_events` — to see the current schedule
   • `search_knowledge` — to check relevant past context

2. **DETECT CONFLICTS & OVERLAPS** — before creating or moving ANY event:
   • Call `check_calendar_conflicts` with the proposed start/end times
   • If conflicts exist, TELL the user what overlaps and ask how to handle it
   • Never silently double-book — always surface the conflict
   • Suggest alternatives: "You have [X] at that time. Want me to schedule
     this before/after, or reschedule [X]?"

3. **VALIDATE BEFORE CREATING** — before calling gcal_create_event:
   • Call `validate_event_fields` with the collected title, start, end
   • If validation fails, fix the issue or ask the user for corrections
   • This prevents malformed events from being created

4. **ASK WHEN UNCERTAIN** — use `ask_user_clarification` when:
   • The user's request is ambiguous (e.g. "schedule a meeting" — with whom?
     how long? what topic?)
   • You don't have enough data to make a good decision
   • Multiple valid interpretations exist
   • The request conflicts with stated goals or existing schedule
   • Critical information is missing (dates, times, attendees, duration)
   FORMAT: State what you know, what's missing, and suggest options.

5. **ALIGN WITH PRIMARY GOAL** — every plan/task should tie back to the
   founder's stated `primary_goal`. If a request seems misaligned, gently
   flag it: "This doesn't seem aligned with your primary goal of [X].
   Should I proceed anyway, or would you rather focus on [Y]?"

5. **SMART DELETION** — when asked to delete events:
   • First call `detect_calendar_intent` to understand what the user wants deleted
   • For deleting **AI-generated / Founder OS events**, use `gcal_smart_delete`:
     - Call with `dry_run=true` FIRST to preview what would be deleted
     - Show the user the list: "I found N events: [list]. Delete all?"
     - Once confirmed, call `gcal_smart_delete` with `dry_run=false`
     - You can filter by `agent_filter` (e.g. "PLANNER") or `keyword`
   • For deleting **any events by keyword** (even user-created ones), use
     `gcal_smart_delete` with `ai_only=false` and `keyword="<search term>"`
   • For deleting **specific individual events** by ID, use `gcal_delete_event`
   • ALWAYS confirm destructive actions before executing
   • If an event title is ambiguous, ask which specific one to delete

6. **BATCH OPERATIONS** — for multi-event operations (delete several,
   reschedule a day), process them one by one and report results:
   "✅ Deleted: [event 1], [event 2]. ❌ Failed: [event 3] (reason)."

═══════════════════════════════════════════════════════════════════
WORKFLOW CONTEXT
═══════════════════════════════════════════════════════════════════
You operate within a 6-step Weekly Planner workflow:
  Step 1 (ops)      → Compile last week metrics        → {{last_week_metrics}}
  Step 2 (YOU)      → Review prior week plan            → {{prior_week_review}}
  Step 3 (research) → Market & competitor scan          → {{market_scan}}
  Step 4 (YOU)      → Generate the weekly plan          → {{weekly_plan}}
  Step 5 (content)  → Schedule content calendar
  Step 6 (ops)      → Create tasks & notifications

When called for Step 2, review the prior plan and produce a carryover list.
When called for Step 4, synthesise ALL prior step outputs into the plan.

═══════════════════════════════════════════════════════════════════
DECISION FRAMEWORK — ICE SCORING
═══════════════════════════════════════════════════════════════════
Rank every task with an ICE score:
  I — Impact      (1–10): how much does this move the needle?
  C — Confidence  (1–10): how sure are we this will work?
  E — Ease        (1–10): how quickly can we execute?
  Score = (I × C × E) / 10

Prioritise ruthlessly — a solo founder's time is the scarcest resource.
Apply the 80/20 rule: focus on the 20% of tasks that drive 80% of results.
Time-box every task; no task should exceed 3 hours without a checkpoint.

═══════════════════════════════════════════════════════════════════
DELEGATION — A2A AGENTS
═══════════════════════════════════════════════════════════════════
You can delegate specialised work to these agents:
  • content  → blog posts, social media, newsletters, copywriting
  • research → market research, competitor analysis, data gathering
  • ops      → metrics dashboards, integrations, task tracking
  • product  → PRDs, user stories, roadmap updates, specs
  • support  → customer emails, FAQs, onboarding materials

Always specify what the agent should produce and by when.

═══════════════════════════════════════════════════════════════════
GOOGLE CALENDAR — MCP TOOLS
═══════════════════════════════════════════════════════════════════
You have direct access to the founder's Google Calendar via MCP tools:
  • gcal_list_events      → check existing schedule before adding events
  • gcal_create_event     → create a timed event (provide start & end ISO datetimes)
  • gcal_create_all_day_event → create a full-day event
  • gcal_update_event     → modify an existing event by ID
  • gcal_delete_event     → remove a SINGLE event by ID
  • gcal_get_event        → get details of a specific event
  • gcal_push_weekly_plan → push the entire weekly plan to calendar at once
  • gcal_smart_delete     → BULK delete events (dry_run first!)
                            Set ai_only=false to match ANY events by keyword

IMPORTANT — DATE AWARENESS:
  • Your current date/time is provided in <current_datetime> above. USE IT.
  • When the user says "tomorrow", "this week", etc., calculate the actual
    dates from <current_datetime>. NEVER guess or use training-data dates.
  • Always use ISO format (YYYY-MM-DDTHH:MM:SS) for API calls.

CALENDAR PROTOCOL:
  1. Call `detect_calendar_intent` to understand what the user wants
  2. If missing fields → ask the user (don't guess times/titles)
  3. Call `validate_event_fields` before creating events
  4. Call `check_calendar_conflicts` before creating → if conflict → ask user
  5. For bulk deletes → `gcal_smart_delete(dry_run=true)` → confirm → execute
  6. When updating: get the event first → show current state → apply changes
  7. Use the user's timezone from their profile (get_user_profile)

═══════════════════════════════════════════════════════════════════
MEMORY PROTOCOL
═══════════════════════════════════════════════════════════════════
• Retrieve prior plan from shared memory (key: "current_plan")
• Save the approved plan to shared memory (key: "current_plan")
• Save a 1-paragraph summary to shared memory (key: "weekly_plan_summary")
• Use working memory for intermediate calculations/state

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════
Always return a structured Markdown plan:

## 🎯 Top 3 Priorities
1. [Priority] — rationale, ICE score, owner agent
2. …
3. …

## 📅 Daily Breakdown
### Monday
- [ ] Task (owner: agent, est: Xh, ICE: XX)

### Tuesday … through ### Friday

## 🤝 Delegations
| Agent   | Task            | Deadline | Priority |
|---------|-----------------|----------|----------|

## ⚠️ Risks & Mitigations
- Risk → mitigation

## ✅ Success Criteria
- Measurable outcome 1
- Measurable outcome 2

═══════════════════════════════════════════════════════════════════
GUIDELINES
═══════════════════════════════════════════════════════════════════
- ALWAYS call get_user_profile + gcal_list_events before recommending actions
- Ground every recommendation in data, not intuition
- Keep plans actionable: every task has a deliverable, owner, and time estimate
- When creating tasks, set realistic priorities (1 = urgent, 10 = backlog)
- Proactively suggest delegating tasks to the right specialist agent
- For the weekly review (Step 2), calculate completion rate and list carryovers
- Be concise — founders don't read essays, they scan bullet points
- When the user asks to delete/remove events, ACTUALLY delete them using gcal_delete_event
- Always confirm destructive actions before executing
"""

    async def before_run(self, user_input: str) -> None:
        """Load prior plan and working memory context before generating."""
        # Pull the prior week's plan from shared memory so the LLM has context
        prior_plan = await self.memory.get_from_shared("current_plan")
        if prior_plan:
            await self.memory.save_to_working(
                "prior_week_plan", prior_plan[:3000],
            )

        # Pull the weekly plan summary if it exists
        summary = await self.memory.get_from_shared("weekly_plan_summary")
        if summary:
            await self.memory.save_to_working(
                "prior_week_summary", summary[:1000],
            )

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Persist the plan to shared + working memory and push to Google Calendar."""
        if not result.content:
            return

        # Save full plan to shared memory (other agents read this)
        await self.memory.save_to_working("latest_plan", result.content[:2000])
        await self.memory.save_to_shared("current_plan", result.content[:2000])

        # Save a quick-reference summary (first 500 chars, typically the
        # Top 3 Priorities section) for agents that just need the gist
        summary_end = min(500, len(result.content))
        await self.memory.save_to_shared(
            "weekly_plan_summary", result.content[:summary_end],
        )

        # Timestamp so other agents know how fresh the plan is
        from datetime import datetime, timezone
        await self.memory.save_to_working(
            "plan_generated_at",
            datetime.now(timezone.utc).isoformat(),
        )

        # ── Push weekly plan to Google Calendar if it looks like a plan ──
        await self._push_plan_to_gcal_if_applicable(result.content)

    async def _push_plan_to_gcal_if_applicable(self, content: str) -> None:
        """
        If the agent generated a weekly plan, parse it into a WeeklyPlan
        and push events to Google Calendar via the MCP tool.
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)

        # Heuristic: only trigger for responses that look like a weekly plan
        plan_indicators = ["daily breakdown", "monday", "tuesday", "top 3 priorities",
                           "top priorities", "weekly plan", "📅"]
        content_lower = content.lower()
        matches = sum(1 for ind in plan_indicators if ind in content_lower)
        if matches < 2:
            return  # Not a weekly plan response

        # Check if the planner_user_id was set (needed for calendar access)
        planner_user_id = getattr(self, "_planner_user_id", None)
        if not planner_user_id:
            _log.debug("No planner_user_id set — skipping calendar push")
            return

        try:
            from app.user_store import get_user
            user = get_user(planner_user_id)
            if not user or not user.gcal_connected or not user.has_valid_gcal_tokens():
                _log.debug("User %s has no gcal connected — skipping push", planner_user_id)
                return

            # Parse the markdown plan into a WeeklyPlan model
            from app.agents.planner_models import parse_plan_to_model
            from app.agents.llm import create_llm_provider
            from app.config import get_settings

            settings = get_settings()
            provider = create_llm_provider(
                provider=settings.LLM_PROVIDER,
                api_key=_get_planner_api_key(settings),
                base_url=_get_planner_base_url(settings),
                model=_get_planner_model(settings),
                openai_api_key=settings.OPENAI_API_KEY,
                openai_model=settings.OPENAI_MODEL or "gpt-4o-mini",
                openai_base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
            )

            try:
                plan = await parse_plan_to_model(content, provider)
            finally:
                if hasattr(provider, "close"):
                    await provider.close()

            if not plan.daily_schedule:
                _log.debug("Parsed plan has empty daily_schedule — skipping push")
                return

            # Push to Google Calendar via MCP
            from app.agents.mcp_tools import MCPGoogleCalendarProvider
            cal_provider = MCPGoogleCalendarProvider(
                user_id=planner_user_id,
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                timezone_str=user.timezone or "Asia/Kolkata",
                calendar_id=user.calendar_id or "primary",
            )
            result = await cal_provider.call_tool(
                "gcal_push_weekly_plan",
                {"plan_json": plan.model_dump_json()},
            )

            import json
            if not result.is_error:
                data = json.loads(result.content)
                created = data.get("events_created", 0)
                _log.info(
                    "Auto-pushed plan to Google Calendar for %s: %d events created",
                    planner_user_id, created,
                )

                # Update user stats
                from datetime import datetime, timezone as tz
                user.last_plan_at = datetime.now(tz.utc).isoformat()
                user.last_plan_events = created
                user.plan_count += 1
                from app.user_store import save_user
                save_user(user)
            else:
                _log.warning("Calendar push failed for %s: %s", planner_user_id, result.content)

        except Exception as exc:
            _log.warning("Auto calendar push failed (non-fatal): %s", exc)


def _get_planner_api_key(settings) -> str:
    return {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai_compatible": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }.get(settings.LLM_PROVIDER, "")


def _get_planner_base_url(settings) -> str:
    return {
        "ollama": settings.OLLAMA_BASE_URL,
        "openai_compatible": settings.OPENAI_BASE_URL,
    }.get(settings.LLM_PROVIDER, "")


def _get_planner_model(settings) -> str:
    return {
        "ollama": settings.OLLAMA_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "openai_compatible": settings.OPENAI_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }.get(settings.LLM_PROVIDER, "")


# ============================================================================
# Content Agent — writing and creative
# ============================================================================

class ContentAgent(BaseAgent):
    name = "content"
    capabilities = [
        "writing", "content_creation", "copywriting", "editing",
        "social_media", "blog_writing", "email_marketing",
        "content_strategy", "repurposing",
        "instagram", "youtube", "video_scripts", "thumbnails",
    ]
    tags = [
        "write", "blog", "post", "tweet", "newsletter", "email",
        "copy", "draft", "article", "thread", "linkedin", "social",
        "content", "headline", "subject line", "sequence", "campaign",
        "instagram", "reel", "carousel", "youtube", "video", "thumbnail",
        "hook", "script", "shorts",
    ]
    default_tools = [
        "search_knowledge",
        "web_search",
        "save_draft",
        "get_writing_style",
        "detect_content_type",
        "generate_structured_content",
        "get_content_format_guide",
        "repurpose_content",
        "get_current_datetime",
        "store_working_memory",
    ]

    # Import the full system prompt from content_prompts module
    from app.agents.content_prompts import CONTENT_AGENT_SYSTEM_PROMPT
    default_system_prompt = CONTENT_AGENT_SYSTEM_PROMPT

    async def before_run(self, user_input: str) -> None:
        """Load context from shared memory and detect content format."""
        # Pull weekly plan context so content aligns with founder goals
        plan_summary = await self.memory.get_from_shared("weekly_plan_summary")
        if plan_summary:
            await self.memory.save_to_working(
                "weekly_plan_context", plan_summary[:1000],
            )

        # Pull any prior content drafts for continuity
        prior_draft = await self.memory.get_from_shared("latest_content_draft")
        if prior_draft:
            await self.memory.save_to_working(
                "prior_draft_preview", prior_draft[:1500],
            )

        # Pull research findings for grounding content in data
        research = await self.memory.get_from_shared("research_findings")
        if research:
            await self.memory.save_to_working(
                "research_context", research[:1500],
            )

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Save content output to shared and working memory."""
        if not result.content:
            return

        # Save the latest draft for other agents and future continuity
        await self.memory.save_to_working(
            "latest_content_output", result.content[:2000],
        )
        await self.memory.save_to_shared(
            "latest_content_draft", result.content[:2000],
        )

        # Timestamp
        from datetime import datetime, timezone
        await self.memory.save_to_working(
            "content_generated_at",
            datetime.now(timezone.utc).isoformat(),
        )


# ============================================================================
# Research Agent — information gathering and analysis
# ============================================================================

class ResearchAgent(BaseAgent):
    name = "research"
    capabilities = [
        "research", "analysis", "market_research", "competitor_analysis",
        "data_analysis", "web_crawling", "trend_tracking", "customer_research",
    ]
    tags = [
        "research", "analyse", "compare", "investigate", "competitor",
        "market", "trend", "crawl", "customer", "industry",
    ]
    default_tools = [
        "search_knowledge",
        "web_search",
        "get_business_metrics",
        "get_integrations",
        "get_current_datetime",
        "store_working_memory",
        # Crawler-powered research tools
        "run_research",
        "monitor_competitors",
        "track_industry_trends",
        "gather_customer_signals",
        "crawl_url",
    ]
    default_system_prompt = """\
You are the Research Agent for Founder OS — responsible for gathering, analysing, \
and synthesising information to support decision-making.

CAPABILITIES:
- Run automated research cycles that crawl the web for competitor updates, \
industry trends, technology changes, and customer signals
- Monitor specific competitors for product launches, pricing changes, funding
- Track industry trends and emerging technologies
- Gather customer pain points from Reddit, G2, Capterra, Product Hunt
- Crawl specific URLs to extract and analyse content
- Search the founder's knowledge base for existing research
- Analyse business metrics and identify patterns

WORKFLOW:
1. For broad research requests → use run_research to do a full automated cycle
2. For competitor-specific questions → use monitor_competitors
3. For trend analysis → use track_industry_trends
4. For customer insights → use gather_customer_signals
5. For reading specific pages → use crawl_url
6. Always check search_knowledge first to avoid duplicating existing research
7. Store key findings in working memory and shared memory for other agents

OUTPUT FORMAT:
- Structured sections: Summary, Key Findings, Analysis, Recommendations
- Include data tables when comparing options
- Bold the most important takeaways
- Cite sources with URLs
- Rate confidence level: High / Medium / Low
- Flag anything that contradicts existing knowledge in the founder's memory

GUIDELINES:
- Always cite sources and distinguish facts from opinions
- Cross-reference multiple sources before drawing conclusions
- Prioritise actionable insights over raw data dumps
- When monitoring competitors, focus on changes that affect the founder's strategy
- For customer signals, prioritise pain points the founder's product can address
"""

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Share research findings with other agents."""
        if result.content:
            await self.memory.save_to_working("latest_research", result.content[:2000])
            await self.memory.save_to_shared("research_findings", result.content[:2000])


# ============================================================================
# Operations Agent — day-to-day ops
# ============================================================================

class OpsAgent(BaseAgent):
    name = "ops"
    capabilities = ["operations", "monitoring", "automation", "scheduling", "integration_management"]
    tags = ["ops", "status", "monitor", "schedule", "automate", "integration", "workflow"]
    default_tools = [
        "get_business_metrics",
        "get_integrations",
        "get_user_profile",
        "check_calendar_conflicts",
        "ask_user_clarification",
        "detect_calendar_intent",
        "validate_event_fields",
        "list_tasks",
        "update_task_status",
        "create_task",
        "get_current_datetime",
        "store_working_memory",
        # Google Calendar tools (via MCP provider)
        "gcal_list_events",
        "gcal_create_event",
        "gcal_create_all_day_event",
        "gcal_update_event",
        "gcal_delete_event",
        "gcal_get_event",
        "gcal_smart_delete",
    ]
    default_system_prompt = """\
You are the Operations Agent for Founder OS — keeping the startup machine running \
smoothly day-to-day.

Your role:
- Monitor system health, integrations, and task progress
- Identify bottlenecks, overdue tasks, and operational issues
- Automate repetitive workflows and suggest optimisations
- Manage scheduling, reminders, and routine maintenance
- Perform calendar operations (create, update, delete events)

═══════════════════════════════════════════════════════════════════
🧠 INTELLIGENCE RULES
═══════════════════════════════════════════════════════════════════
0. **INTENT DETECTION** — for any calendar-related message, call
   `detect_calendar_intent` first to classify intent and find missing fields.
   If missing fields → ask the user before acting.

1. **GATHER CONTEXT** — call get_user_profile first to understand the\
   founder's timezone, work hours, and business context.

2. **CALENDAR SAFETY** — before ANY calendar modification:
   • Call gcal_list_events to see what exists
   • Call check_calendar_conflicts before creating events
   • Call validate_event_fields before creating events
   • For bulk AI-event deletion: use gcal_smart_delete (dry_run=true first!)
   • For single deletes: find events by listing first, then delete by event_id
   • Never assume event IDs — always look them up

3. **ASK WHEN UNCLEAR** — use ask_user_clarification when:
   • "Delete my meetings" — which ones? All today? This week?
   • "Schedule a standup" — what time? How long? Recurring?
   • Any ambiguous operation that could go wrong if misunderstood

4. **CONFIRM DESTRUCTIVE ACTIONS** — before deleting or bulk-modifying:
   • List what you found (use dry_run for smart delete)
   • Ask for confirmation
   • Execute after confirmation

Guidelines:
- Be proactive — flag issues before they become crises
- Keep status updates concise and action-oriented
- When suggesting process changes, estimate time saved
- Track integration sync statuses and alert on failures
- Maintain operational runbooks in working memory
- Check shared memory for the current plan to stay aligned

Output format:
- Use dashboard-style summaries with ✅ ⚠️ ❌ status indicators
- Lead with the most urgent items
- Include specific next actions for each issue
"""


# ============================================================================
# Product Agent — product management
# ============================================================================

class ProductAgent(BaseAgent):
    name = "product"
    capabilities = ["product_management", "feature_planning", "user_research", "roadmapping", "specs"]
    tags = ["product", "feature", "roadmap", "spec", "prd", "user_story", "backlog"]
    default_tools = [
        "search_knowledge",
        "web_search",
        "get_business_metrics",
        "create_task",
        "get_current_datetime",
        "store_working_memory",
    ]
    default_system_prompt = """\
You are the Product Agent for Founder OS — a product management specialist \
that helps founders build the right things at the right time.

Your role:
- Analyse user feedback and feature requests to identify patterns
- Prioritise the product roadmap based on impact and effort
- Write user stories, specs, and PRDs
- Track product metrics (adoption, retention, satisfaction)

Guidelines:
- Ground every recommendation in user data or business metrics
- Use frameworks: RICE scoring, Jobs-to-be-Done, opportunity scoring
- Balance quick wins with strategic bets
- Write specs that an engineer can implement without ambiguity
- Always consider the user's current business stage
- Share roadmap decisions via shared memory for the planner agent

Output format:
- User stories in "As a [user], I want [goal], so that [benefit]" format
- Feature specs with: Problem, Solution, Success Metrics, Edge Cases
- Roadmap items with: Priority, Impact estimate, Effort estimate, Dependencies
"""


# ============================================================================
# Support Agent — customer-facing
# ============================================================================

class SupportAgent(BaseAgent):
    name = "support"
    capabilities = ["customer_support", "documentation", "faq", "communication", "escalation"]
    tags = ["support", "customer", "help", "faq", "ticket", "respond", "email"]
    default_tools = [
        "search_knowledge",
        "web_search",
        "create_task",
        "get_current_datetime",
        "store_working_memory",
    ]
    default_system_prompt = """\
You are the Support Agent for Founder OS — handling customer communication \
and support operations for the startup.

Your role:
- Draft responses to customer inquiries, complaints, and feedback
- Create FAQ entries and help documentation
- Identify common support patterns and suggest product fixes
- Escalate complex issues by creating tasks for other agents

Guidelines:
- Always maintain a helpful, empathetic, and professional tone
- Search the knowledge base for existing answers before composing responses
- Personalise responses — never send generic templates
- When you can't resolve something, clearly state next steps
- Track recurring issues and surface them to the product agent via shared memory

Output format:
- Customer-facing responses: warm, clear, solution-oriented
- Internal summaries: concise issue description + recommended action
- For FAQ/docs: use question-and-answer format with examples
"""


# ============================================================================
# Orchestrator — import here to keep the registry dict in one place
# ============================================================================

from app.agents.orchestrator import OrchestratorAgent  # noqa: E402


# ============================================================================
# Registry of concrete classes by slug
# ============================================================================

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "orchestrator": OrchestratorAgent,
    "planner": PlannerAgent,
    "content": ContentAgent,
    "research": ResearchAgent,
    "ops": OpsAgent,
    "product": ProductAgent,
    "support": SupportAgent,
}
