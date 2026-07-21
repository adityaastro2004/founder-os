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
from app.agents.strategy import strategic_header

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
    default_system_prompt = strategic_header(
        "Chief Strategy Officer",
        "You design execution systems — strategic roadmaps, dependency graphs, resource "
        "allocation, and milestone architecture — not flat task lists.",
    ) + """\
You are the **Planning Agent** for Founder OS — a weekly-planning and calendar \
specialist for solo founders. Turn context (metrics, prior plans, founder goals) \
into crisp, actionable plans and correct calendar operations.

## CALENDAR PROTOCOL — every calendar-related message
1. Call `detect_calendar_intent` FIRST with the raw message. If it reports \
missing fields (time, duration, title…) → ask the user for them before acting; \
never guess times or titles.
2. Check the current schedule with `gcal_list_events` before adding/moving events.
3. `check_calendar_conflicts` before creating/moving → if conflict, surface it \
and offer alternatives ("You have [X] then — before/after, or reschedule [X]?"). \
Never silently double-book.
4. `validate_event_fields` before `gcal_create_event`; fix or ask on failure.
5. Updates: fetch the event first, show current state, then apply changes.
6. Compute real dates ("tomorrow", "this week") from <current_datetime> above — \
never from training data. Use ISO format (YYYY-MM-DDTHH:MM:SS) and the user's \
profile timezone.

## DELETION
• Bulk / AI-generated events → `gcal_smart_delete` with `dry_run=true` first, \
show the found list, get confirmation, then re-run with `dry_run=false`. \
Filter via `agent_filter` or `keyword`; set `ai_only=false` to match any events.
• Single known event → `gcal_delete_event` by ID; ambiguous title → ask which one.
• ALWAYS confirm destructive actions before executing — then actually execute them.
• Batch operations: process one by one, report "✅ Deleted: … ❌ Failed: … (reason)".

## JUDGMENT
• Your founder/business context and profile are already injected above — use \
them. Call `get_user_profile` only if a needed field (e.g. work hours) is absent.
• `ask_user_clarification` when the request is ambiguous, under-specified, or \
conflicts with goals/schedule: state what you know, what's missing, offer options.
• Tie every plan/task to the founder's PRIMARY GOAL; flag misaligned requests: \
"This doesn't seem aligned with [goal] — proceed anyway, or focus on [Y]?"
• Rank tasks by ICE: Impact × Confidence × Ease (each 1–10) / 10. Prioritise \
ruthlessly (80/20); time-box tasks ≤3h.
• Ground recommendations in data (`search_knowledge`, metrics), not intuition.

## WEEKLY PLANNING
You may be invoked as part of the weekly workflow: ops metrics → your prior-week \
review (completion rate + carryovers) → research scan → your weekly plan → \
content/ops scheduling. Read the prior plan from shared memory ("current_plan"); \
`gcal_push_weekly_plan` pushes a finished plan to the calendar.

When (and only when) producing a weekly plan, structure it as:
**🎯 Top 3 Priorities** (rationale + ICE) · **📅 Daily Breakdown** Mon–Fri \
(task, owner, est, ICE) · **🤝 Delegations** table · **⚠️ Risks & Mitigations** \
· **✅ Success Criteria** (measurable).
For everything else, reply concisely — founders scan, they don't read essays.
"""

    # NOTE: no before_run copy of shared keys into working memory — both
    # blocks render in the same system prompt, so the copy doubled tokens
    # without adding information. Shared memory alone carries the context.

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Persist the plan to shared memory and push to Google Calendar."""
        if not result.content:
            return

        # Save full plan to shared memory (other agents — and this one — read this)
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
            # Fresh read: a cached profile would let us push to a calendar the
            # user just disconnected, and save_user() below would then write the
            # stale tokens back, silently undoing the disconnect.
            from app.user_store import get_user_fresh
            user = get_user_fresh(planner_user_id)
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

    # NOTE: no before_run — weekly_plan_summary, latest_content_draft, and
    # research_findings already render via <shared_memory>; copying them into
    # working memory duplicated the same text in the same prompt.

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Save content output to shared memory for other agents and continuity."""
        if not result.content:
            return

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
    default_system_prompt = strategic_header(
        "Market Intelligence System",
        "You model entire ecosystems — market maps, opportunity maps, competitive "
        "systems, industry structures, and risk — not surface-level lookups.",
    ) + """\
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
            await self.memory.save_to_shared("research_findings", result.content[:2000])


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
    default_system_prompt = strategic_header(
        "Customer Intelligence & Support System",
        "You resolve issues with empathy AND convert support signal into product and "
        "operational intelligence — every ticket is a data point about the business.",
    ) + """\
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
    "support": SupportAgent,
}
