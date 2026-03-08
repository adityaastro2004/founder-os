"""
Founder OS — User Profile Intelligence
========================================
Hybrid service that:

1. **Extracts** atomic insights using lightweight keyword/pattern rules on
   every conversation turn — zero LLM calls, pure DB writes.
2. **Rolls up** (on-demand, not every message) insights into a deep per-user
   profile via LLM synthesis when explicitly triggered.
3. **Detects cross-user patterns** for business improvement (on-demand LLM).
4. **Generates content ideas** from aggregated insights (on-demand LLM).
5. **Serves cached profile context** to agents from the DB — no LLM needed.

Cost model:
  - Per interaction: 0 LLM calls (pattern rules + DB writes only)
  - On-demand synthesis: 1 LLM call per rebuild (user or cron triggered)
  - Business patterns / content ideas: 1 LLM call each (admin triggered)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessInsight,
    ContentIdea,
    UserInsight,
    UserProfileIntel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Lightweight rule-based insight extraction (NO LLM)
# ============================================================================

# Patterns: (compiled regex, insight_type, sentiment, confidence)
# Order matters — first match wins for a given sentence.

_LIKE_PHRASES = [
    r"\b(?:i (?:really )?(?:like|love|enjoy|prefer|appreciate)\b)",
    r"\b(?:this is (?:great|awesome|perfect|excellent|amazing|wonderful))\b",
    r"\b(?:that(?:'s| is) (?:exactly|perfect|great|awesome))\b",
    r"\b(?:keep (?:doing|up|it)\b)",
    r"\b(?:more (?:of )?this)\b",
]

_DISLIKE_PHRASES = [
    r"\b(?:i (?:don'?t|do not) (?:like|want|need|enjoy))\b",
    r"\b(?:(?:stop|quit|don'?t) (?:doing|giving|sending|making))\b",
    r"\b(?:too (?:much|many|long|short|verbose|brief|formal|casual))\b",
    r"\b(?:(?:this|that)(?:'s| is) (?:not|wrong|bad|useless|unhelpful|annoying))\b",
    r"\b(?:i hate)\b",
]

_PAIN_PHRASES = [
    r"\b(?:i(?:'m| am) (?:struggling|stuck|frustrated|confused|overwhelmed))\b",
    r"\b(?:(?:it(?:'s| is)|this is) (?:hard|difficult|challenging|impossible|painful))\b",
    r"\b(?:my (?:biggest )?(?:problem|issue|challenge|blocker|struggle) (?:is|with))\b",
    r"\b(?:can'?t (?:figure|find|get|make|manage|understand|do))\b",
    r"\b(?:having (?:trouble|issues|problems|difficulty))\b",
]

_GOAL_PHRASES = [
    r"\b(?:i (?:want|need|wish|hope) to)\b",
    r"\b(?:my goal is)\b",
    r"\b(?:i(?:'m| am) (?:trying|planning|aiming|looking) to)\b",
    r"\b(?:help me (?:with|to|figure|build|create|get|reach|achieve))\b",
    r"\b(?:i need)\b",
]

_EXPECTATION_PHRASES = [
    r"\b(?:i expect)\b",
    r"\b(?:(?:should|could you) (?:be|give|provide|include|make))\b",
    r"\b(?:i(?:'d| would) (?:like|prefer|expect|want) (?:you to|it to|more|less))\b",
]

_TONE_PHRASES = [
    r"\b(?:(?:be |keep it |make it )?(?:more )?(?:casual|formal|brief|concise|detailed|friendly|professional|direct|simple))\b",
    r"\b(?:(?:less |not so )(?:formal|casual|verbose|wordy|brief|detailed))\b",
    r"\b(?:(?:can you )?(?:speak|talk|write|respond) (?:more )?(?:casually|formally|briefly|simply))\b",
]

_TOPIC_PHRASES = [
    r"\b(?:(?:tell|teach|help|show) me (?:about|how|more about))\b",
    r"\b(?:i(?:'m| am) (?:interested|curious) (?:in|about))\b",
    r"\b(?:what (?:about|is|are|do you (?:think|know) about))\b",
    r"\b(?:how (?:do(?:es)?|can|should|to) )\b",
]

_FEEDBACK_POSITIVE = [
    r"\b(?:thanks?(?:\s+(?:you|so much|a lot))?)\b",
    r"\b(?:perfect|excellent|amazing|wonderful|brilliant|fantastic|helpful)\b",
    r"\b(?:(?:this|that)(?:'s| is) (?:exactly )?what i (?:needed|wanted))\b",
    r"\b(?:great (?:job|work|answer|response))\b",
    r"\b(?:well done|nice one|good job)\b",
]

_FEEDBACK_NEGATIVE = [
    r"\b(?:(?:that(?:'s| is)|this is) (?:not (?:what|right|correct|helpful)))\b",
    r"\b(?:(?:wrong|incorrect|inaccurate|useless|unhelpful) (?:answer|response)?)\b",
    r"\b(?:try again)\b",
    r"\b(?:no,? (?:i (?:meant|said|asked|want)))\b",
    r"\b(?:you (?:misunderstood|got it wrong|missed))\b",
]

# Compile all patterns once at import time
_PATTERNS: list[tuple[re.Pattern, str, str, float]] = []
for _phrases, _type, _sent, _conf in [
    (_LIKE_PHRASES, "like", "positive", 0.80),
    (_DISLIKE_PHRASES, "dislike", "negative", 0.80),
    (_PAIN_PHRASES, "pain_point", "negative", 0.85),
    (_GOAL_PHRASES, "goal", "neutral", 0.75),
    (_EXPECTATION_PHRASES, "expectation", "neutral", 0.70),
    (_TONE_PHRASES, "tone_signal", "neutral", 0.75),
    (_TOPIC_PHRASES, "topic_interest", "neutral", 0.65),
    (_FEEDBACK_POSITIVE, "feedback", "positive", 0.80),
    (_FEEDBACK_NEGATIVE, "feedback", "negative", 0.80),
]:
    for _p in _phrases:
        _PATTERNS.append((re.compile(_p, re.IGNORECASE), _type, _sent, _conf))


def _extract_insights_rules(
    user_message: str,
) -> list[dict[str, Any]]:
    """
    Pure-Python pattern matcher.  Returns a list of insight dicts
    extracted from the user's message.  Zero LLM calls.
    """
    if not user_message or len(user_message.strip()) < 5:
        return []

    msg = user_message.strip()
    # Split into sentences for more granular matching
    sentences = re.split(r'[.!?\n]+', msg)
    seen_values: set[str] = set()
    insights: list[dict[str, Any]] = []

    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 4:
            continue
        for pattern, itype, sentiment, confidence in _PATTERNS:
            if pattern.search(s):
                # Use the sentence as the insight value — trim to keep atomic
                value = s[:200].strip()
                if value in seen_values:
                    continue
                seen_values.add(value)
                insights.append({
                    "type": itype,
                    "value": value,
                    "confidence": confidence,
                    "sentiment": sentiment,
                })
                break  # one match per sentence

    return insights


# ============================================================================
# LLM prompt templates — only used for on-demand operations
# ============================================================================

PROFILE_SYNTHESIS_PROMPT = """\
You are an expert user-research analyst. Build a comprehensive user profile
from the collected insights below.

<insights>
{insights_json}
</insights>

<existing_profile>
{existing_profile_json}
</existing_profile>

Create an UPDATED profile JSON with these fields:
{{
  "preferred_tone": "how this user likes to be spoken to (style, formality, pace)",
  "communication_style": "how they communicate (concise vs detailed, emotional vs analytical)",
  "likes": ["specific things they enjoy or respond well to"],
  "dislikes": ["specific things they dislike or react negatively to"],
  "topics_of_interest": ["topics they frequently ask about or show interest in"],
  "pain_points": ["specific challenges, frustrations, blockers they face"],
  "expectations": ["what they expect from the AI system"],
  "goals": ["their stated or implied objectives"],
  "profile_summary": "A 2-3 sentence natural language summary of who this user is, what they care about, and how they work",
  "conversation_guide": "Specific instructions for AI agents: preferred tone, what to avoid, what to emphasise, how to structure responses for this user. Be actionable and specific."
}}

Rules:
- MERGE new insights with the existing profile — don't lose existing data.
- Remove duplicates but keep the most specific version.
- If new insights contradict old ones, prefer the newer insight.
- Keep each list to max 15 items — prioritise by frequency and recency.
- The conversation_guide should be ACTIONABLE — agents will use it directly.

Return ONLY valid JSON, no markdown fences."""

BUSINESS_PATTERNS_PROMPT = """\
You are a business intelligence analyst. Analyse these user insights
collected across multiple users and identify patterns.

<insights>
{insights_json}
</insights>

Identify cross-user patterns and return a JSON array of business insights:
{{
  "type": one of "common_pain_point", "trending_topic", "popular_request",
          "content_opportunity", "workflow_optimization", "feature_request",
          "satisfaction_driver", "churn_risk",
  "title": "short descriptive title",
  "description": "detailed description of the pattern",
  "user_count": number of users exhibiting this pattern,
  "frequency": total occurrences,
  "impact_score": 0.0-1.0 estimated business impact,
  "recommended_actions": ["specific action 1", "action 2"]
}}

Rules:
- A pattern needs ≥2 users OR ≥3 occurrences from 1 user to be included.
- Focus on actionable insights, not obvious observations.
- Score impact based on: # of users affected, severity, ease of fix.
- Include content opportunities — what topics should we create content about?

Return ONLY valid JSON array, no markdown fences."""

CONTENT_IDEAS_PROMPT = """\
You are a content strategist. Generate content ideas based on these
business insights and user patterns.

<business_insights>
{business_insights_json}
</business_insights>

<user_pain_points>
{pain_points_json}
</user_pain_points>

Generate a JSON array of content ideas:
{{
  "title": "compelling content title",
  "description": "what the content should cover and why it matters",
  "content_type": one of "blog", "instagram", "youtube", "newsletter",
                  "twitter_thread", "case_study", "tutorial",
  "target_audience": "who this is for",
  "hooks": ["hook option 1", "hook option 2"],
  "key_points": ["main point 1", "main point 2", "main point 3"],
  "source_type": one of "user_pain_point", "trending_topic",
                 "popular_question", "success_story",
                 "common_objection", "industry_trend",
  "priority": 1-10 (10 = most important)
}}

Rules:
- Generate 3-8 ideas, prioritised by relevance and potential impact.
- Every idea should directly address a real user need or pattern.
- Include a mix of content types (not all blogs).
- Hooks should be attention-grabbing and specific.

Return ONLY valid JSON array, no markdown fences."""


# ============================================================================
# ProfileIntelligence — the main service
# ============================================================================

class ProfileIntelligence:
    """
    Extracts user insights from conversations, builds deep profiles,
    and generates business intelligence + content ideas.
    """

    def __init__(self, db: AsyncSession, llm_generate: Any) -> None:
        """
        Args:
            db: Async SQLAlchemy session.
            llm_generate: An async callable that accepts (system: str, prompt: str)
                          and returns a string response. This decouples us from
                          the specific LLM provider implementation.
        """
        self._db = db
        self._llm = llm_generate

    # ------------------------------------------------------------------
    # 1. Extract insights from a single interaction (rule-based, no LLM)
    # ------------------------------------------------------------------

    async def extract_insights(
        self,
        user_id: str,
        agent_name: str,
        user_message: str,
        agent_response: str,
        session_id: str | None = None,
        agent_run_id: uuid.UUID | None = None,
    ) -> list[UserInsight]:
        """
        Analyse a conversation turn using lightweight keyword/pattern rules.
        Zero LLM calls — only DB writes.
        """
        insights_data = _extract_insights_rules(user_message)

        records: list[UserInsight] = []
        for item in insights_data:
            record = UserInsight(
                user_id=user_id,
                agent_name=agent_name,
                session_id=session_id,
                agent_run_id=agent_run_id,
                source_message=user_message[:500],
                insight_type=item["type"],
                insight_value=item["value"],
                confidence=Decimal(str(item["confidence"])),
                sentiment=item["sentiment"],
            )
            self._db.add(record)
            records.append(record)

        if records:
            try:
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                return []

        # Also update simple signal counters on the profile
        await self._update_signal_counters(user_id, user_message, agent_response)

        return records

    # ------------------------------------------------------------------
    # 2. Synthesise/roll-up insights into a deep user profile
    # ------------------------------------------------------------------

    async def synthesise_profile(self, user_id: str) -> UserProfileIntel | None:
        """
        Process all unprocessed insights for a user and merge them into
        the user's profile. Uses the LLM to do intelligent merging.
        """
        # Fetch unprocessed insights
        result = await self._db.execute(
            select(UserInsight)
            .where(UserInsight.user_id == user_id, UserInsight.is_processed == False)  # noqa: E712
            .order_by(UserInsight.created_at)
            .limit(100)
        )
        new_insights = result.scalars().all()
        if not new_insights:
            # Nothing new — return existing profile
            return await self._get_or_create_profile(user_id)

        # Get existing profile
        profile = await self._get_or_create_profile(user_id)

        # Build insights JSON for the LLM
        insights_json = json.dumps([
            {
                "type": i.insight_type,
                "value": i.insight_value,
                "confidence": float(i.confidence) if i.confidence else 0.8,
                "sentiment": i.sentiment or "neutral",
                "agent": i.agent_name,
            }
            for i in new_insights
        ], indent=2)

        existing_profile_json = json.dumps({
            "preferred_tone": profile.preferred_tone or "",
            "communication_style": profile.communication_style or "",
            "likes": profile.likes or [],
            "dislikes": profile.dislikes or [],
            "topics_of_interest": profile.topics_of_interest or [],
            "pain_points": profile.pain_points or [],
            "expectations": profile.expectations or [],
            "goals": profile.goals or [],
            "profile_summary": profile.profile_summary or "",
            "conversation_guide": profile.conversation_guide or "",
        }, indent=2)

        prompt = PROFILE_SYNTHESIS_PROMPT.format(
            insights_json=insights_json,
            existing_profile_json=existing_profile_json,
        )

        try:
            raw = await self._llm(
                "You are a user-research analyst. Return only valid JSON.",
                prompt,
            )
            updated = json.loads(raw.strip())
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Profile synthesis failed: %s", exc)
            return profile

        if not isinstance(updated, dict):
            return profile

        # Apply updates
        profile.preferred_tone = updated.get("preferred_tone", profile.preferred_tone)
        profile.communication_style = updated.get("communication_style", profile.communication_style)
        profile.likes = updated.get("likes", profile.likes)
        profile.dislikes = updated.get("dislikes", profile.dislikes)
        profile.topics_of_interest = updated.get("topics_of_interest", profile.topics_of_interest)
        profile.pain_points = updated.get("pain_points", profile.pain_points)
        profile.expectations = updated.get("expectations", profile.expectations)
        profile.goals = updated.get("goals", profile.goals)
        profile.profile_summary = updated.get("profile_summary", profile.profile_summary)
        profile.conversation_guide = updated.get("conversation_guide", profile.conversation_guide)
        profile.version = (profile.version or 0) + 1
        profile.last_analysis_at = datetime.now(timezone.utc)
        profile.updated_at = datetime.now(timezone.utc)

        # Mark insights as processed
        insight_ids = [i.id for i in new_insights]
        await self._db.execute(
            update(UserInsight)
            .where(UserInsight.id.in_(insight_ids))
            .values(is_processed=True, processed_at=datetime.now(timezone.utc))
        )

        try:
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            return None

        return profile

    # ------------------------------------------------------------------
    # 3. Business intelligence — cross-user patterns
    # ------------------------------------------------------------------

    async def analyse_business_patterns(self) -> list[BusinessInsight]:
        """
        Analyse recent insights across ALL users to find patterns.
        Should be called periodically (e.g. daily via Celery task).
        """
        # Fetch recent insights grouped by type
        result = await self._db.execute(
            select(UserInsight)
            .where(UserInsight.created_at >= text("NOW() - INTERVAL '7 days'"))
            .order_by(UserInsight.created_at.desc())
            .limit(500)
        )
        recent = result.scalars().all()
        if len(recent) < 3:
            return []

        insights_json = json.dumps([
            {
                "user_id": i.user_id[:8] + "...",  # anonymised
                "type": i.insight_type,
                "value": i.insight_value,
                "sentiment": i.sentiment or "neutral",
                "agent": i.agent_name,
            }
            for i in recent
        ], indent=2)

        prompt = BUSINESS_PATTERNS_PROMPT.format(insights_json=insights_json)

        try:
            raw = await self._llm(
                "You are a business intelligence analyst. Return only valid JSON array.",
                prompt,
            )
            patterns = json.loads(raw.strip())
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Business pattern analysis failed: %s", exc)
            return []

        if not isinstance(patterns, list):
            return []

        records: list[BusinessInsight] = []
        for p in patterns:
            if not isinstance(p, dict):
                continue
            record = BusinessInsight(
                insight_type=p.get("type", "unknown"),
                title=p.get("title", "")[:500],
                description=p.get("description", ""),
                user_count=p.get("user_count", 1),
                frequency=p.get("frequency", 1),
                impact_score=Decimal(str(min(max(p.get("impact_score", 0.5), 0.0), 1.0))),
                recommended_actions=p.get("recommended_actions", []),
            )
            self._db.add(record)
            records.append(record)

        if records:
            try:
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                return []

        return records

    # ------------------------------------------------------------------
    # 4. Content idea generation from insights
    # ------------------------------------------------------------------

    async def generate_content_ideas(
        self,
        user_id: str | None = None,
    ) -> list[ContentIdea]:
        """
        Generate content ideas from business insights and user pain points.
        If user_id is provided, also personalise ideas for that user.
        """
        # Fetch recent business insights
        bi_result = await self._db.execute(
            select(BusinessInsight)
            .where(BusinessInsight.status == "new")
            .order_by(BusinessInsight.impact_score.desc())
            .limit(20)
        )
        business_insights = bi_result.scalars().all()

        # Fetch common pain points
        pp_result = await self._db.execute(
            select(UserInsight.insight_value, func.count().label("cnt"))
            .where(UserInsight.insight_type.in_(["pain_point", "topic_interest", "goal"]))
            .group_by(UserInsight.insight_value)
            .order_by(text("cnt DESC"))
            .limit(30)
        )
        pain_points = [{"value": row[0], "count": row[1]} for row in pp_result.fetchall()]

        if not business_insights and not pain_points:
            return []

        business_insights_json = json.dumps([
            {
                "type": bi.insight_type,
                "title": bi.title,
                "description": bi.description,
                "user_count": bi.user_count,
                "impact_score": float(bi.impact_score) if bi.impact_score else 0.5,
            }
            for bi in business_insights
        ], indent=2)

        pain_points_json = json.dumps(pain_points, indent=2)

        prompt = CONTENT_IDEAS_PROMPT.format(
            business_insights_json=business_insights_json,
            pain_points_json=pain_points_json,
        )

        try:
            raw = await self._llm(
                "You are a content strategist. Return only valid JSON array.",
                prompt,
            )
            ideas_data = json.loads(raw.strip())
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Content idea generation failed: %s", exc)
            return []

        if not isinstance(ideas_data, list):
            return []

        records: list[ContentIdea] = []
        for idea in ideas_data:
            if not isinstance(idea, dict):
                continue
            record = ContentIdea(
                user_id=user_id,
                title=idea.get("title", "")[:500],
                description=idea.get("description", ""),
                content_type=idea.get("content_type"),
                target_audience=idea.get("target_audience"),
                hooks=idea.get("hooks", []),
                key_points=idea.get("key_points", []),
                source_type=idea.get("source_type", "trending_topic"),
                priority=min(max(idea.get("priority", 5), 1), 10),
            )
            self._db.add(record)
            records.append(record)

        if records:
            try:
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                return []

        return records

    # ------------------------------------------------------------------
    # 5. Get profile context for injection into agent prompts
    # ------------------------------------------------------------------

    async def get_profile_context(self, user_id: str) -> str:
        """
        Build a context block from the user's profile that can be
        injected into any agent's system prompt.
        Returns empty string if no profile exists.
        """
        profile = await self._get_profile(user_id)
        if not profile:
            return ""

        parts = ["<user_profile>"]

        if profile.profile_summary:
            parts.append(f"Summary: {profile.profile_summary}")

        if profile.conversation_guide:
            parts.append(f"\nConversation Guide (FOLLOW THIS): {profile.conversation_guide}")

        if profile.preferred_tone:
            parts.append(f"\nPreferred tone: {profile.preferred_tone}")

        if profile.likes:
            parts.append(f"\nLikes: {', '.join(profile.likes[:10])}")

        if profile.dislikes:
            parts.append(f"\nDislikes (AVOID): {', '.join(profile.dislikes[:10])}")

        if profile.pain_points:
            parts.append(f"\nPain points: {', '.join(profile.pain_points[:8])}")

        if profile.goals:
            parts.append(f"\nGoals: {', '.join(profile.goals[:8])}")

        if profile.topics_of_interest:
            parts.append(f"\nInterests: {', '.join(profile.topics_of_interest[:8])}")

        parts.append("</user_profile>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_profile(self, user_id: str) -> UserProfileIntel | None:
        result = await self._db.execute(
            select(UserProfileIntel).where(UserProfileIntel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_profile(self, user_id: str) -> UserProfileIntel:
        profile = await self._get_profile(user_id)
        if profile:
            return profile
        profile = UserProfileIntel(user_id=user_id)
        self._db.add(profile)
        try:
            await self._db.commit()
            await self._db.refresh(profile)
        except Exception:
            await self._db.rollback()
            # Race condition — try fetching again
            existing = await self._get_profile(user_id)
            if existing:
                return existing
            raise
        return profile

    async def _update_signal_counters(
        self,
        user_id: str,
        user_message: str,
        agent_response: str,
    ) -> None:
        """Update simple positive/negative signal counters and total_interactions."""
        profile = await self._get_or_create_profile(user_id)

        positive_words = {"thanks", "thank you", "perfect", "great", "awesome",
                          "love it", "exactly", "wonderful", "excellent", "helpful"}
        negative_words = {"no", "wrong", "not what i", "that's not", "incorrect",
                          "bad", "useless", "don't", "stop", "redo"}

        msg_lower = user_message.lower()
        pos = any(w in msg_lower for w in positive_words)
        neg = any(w in msg_lower for w in negative_words)

        profile.total_interactions = (profile.total_interactions or 0) + 1
        if pos:
            profile.positive_signals = (profile.positive_signals or 0) + 1
        if neg:
            profile.negative_signals = (profile.negative_signals or 0) + 1

        # Update running satisfaction score
        total = (profile.positive_signals or 0) + (profile.negative_signals or 0)
        if total > 0:
            profile.satisfaction_score = Decimal(str(
                round((profile.positive_signals or 0) / total * 5.0, 2)
            ))

        profile.updated_at = datetime.now(timezone.utc)

        try:
            await self._db.commit()
        except Exception:
            await self._db.rollback()
