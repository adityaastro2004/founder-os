"""
Founder OS — Research Orchestrator
===================================
Ties web crawling to founder's business context.

Reads founder data from planner_users and memory_pages,
generates smart research queries, executes web searches,
scores relevance, and stores findings back to memory.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text as sa_text

from app.crawler.engine import CrawlEngine, SearchResult
from app.crawler.sources import (
    get_competitor_search_queries,
    get_customer_signal_queries,
    get_sources_for_industry,
    get_trend_search_queries,
)
from app.database import async_session
from app.memory.manager import get_memory_manager
from app.log_sanitize import sl

logger = logging.getLogger(__name__)


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class ResearchProfile:
    """Founder's business context for research."""
    user_id: str
    company_name: str
    industry: str
    competitors: list[str]
    technologies: list[str]
    keywords: list[str]
    target_audience: str
    active_goals: list[str]
    recent_topics: list[str]


@dataclass
class ResearchFinding:
    """A single research finding to store."""
    title: str
    content: str
    source_url: str
    category: str  # "competitor", "industry", "technology", "customer", "news"
    relevance_score: float
    entities: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class CompetitorUpdate:
    """Update about a competitor."""
    competitor: str
    title: str
    summary: str
    source_url: str
    change_type: str  # "product_launch", "pricing", "funding", "hiring", "news"


@dataclass
class TrendItem:
    """An industry or technology trend."""
    topic: str
    summary: str
    sources: list[str]
    relevance: float


@dataclass
class CustomerSignal:
    """Customer sentiment or feedback."""
    topic: str
    sentiment: str  # "positive", "negative", "neutral"
    summary: str
    source_url: str
    platform: str  # "reddit", "twitter", "forum", "review_site"


@dataclass
class ResearchReport:
    """Complete research run report."""
    user_id: str
    generated_at: datetime
    competitor_updates: list[CompetitorUpdate]
    trends: list[TrendItem]
    customer_signals: list[CustomerSignal]
    findings_stored: int
    queries_executed: int
    pages_crawled: int


# ============================================================================
# ResearchEngine — Main orchestrator
# ============================================================================

class ResearchEngine:
    """
    Orchestrates research cycles tied to founder's business context.

    Workflow:
      1. build_research_profile() — fetch founder data from DB
      2. _generate_queries() — create smart search queries
      3. search_web() — execute searches
      4. _score_relevance() — filter & score results
      5. _store_finding() — save to memory_pages + knowledge_items
      6. Categorize & return report
    """

    def __init__(self, crawl_engine: CrawlEngine, settings=None):
        self.crawl_engine = crawl_engine
        self.settings = settings

    # ────────────────────────────────────────────────────────────
    # Main API
    # ────────────────────────────────────────────────────────────

    async def build_research_profile(self, user_id: str) -> Optional[ResearchProfile]:
        """
        Build founder's research profile from database.
        Queries planner_users for business context + memory_pages for recent topics.
        """
        try:
            async with async_session() as session:
                # Fetch planner_users row
                planner_user = await session.execute(
                    sa_text(
                        """
                        SELECT user_id, business_name, industry, target_audience
                        FROM planner_users
                        WHERE user_id = :uid
                        """
                    ),
                    {"uid": user_id},
                )
                row = planner_user.first()

                if not row:
                    logger.warning("No planner_users entry for %s", sl(user_id))
                    return None

                company_name = row[1] or "Unknown Company"
                industry = row[2] or "General"
                target_audience = row[3] or ""

                # Fetch recent memory_pages for context
                recent_memories = await session.execute(
                    sa_text(
                        """
                        SELECT title, tags, entities
                        FROM memory_pages
                        WHERE user_id = :uid AND is_active = true
                        ORDER BY occurred_at DESC
                        LIMIT 20
                        """
                    ),
                    {"uid": user_id},
                )

                # Extract keywords from recent memories
                keywords = set()
                recent_topics = []

                for mem_row in recent_memories:
                    title = mem_row[0]
                    tags = mem_row[1] or []
                    entities = mem_row[2] or {}

                    recent_topics.append(title)
                    keywords.update(tags)

                    # Extract entities
                    if isinstance(entities, dict):
                        for entity_list in entities.values():
                            if isinstance(entity_list, list):
                                keywords.update(entity_list)

                # Hardcoded defaults for competitors/technologies
                # In production, these might be stored in memory_pages or a separate table
                competitors = []
                technologies = []

                # Try to extract from recent memories
                if recent_topics:
                    # Simple heuristic: look for competitor names in recent topics
                    for topic in recent_topics[:5]:
                        if "competitor" in topic.lower():
                            competitors.append(topic)

                keywords = list(keywords)[:10]  # Limit to 10

                return ResearchProfile(
                    user_id=user_id,
                    company_name=company_name,
                    industry=industry,
                    competitors=competitors,
                    technologies=technologies,
                    keywords=keywords,
                    target_audience=target_audience,
                    active_goals=[],  # Could fetch from planner_users.goals_this_week
                    recent_topics=recent_topics[:10],
                )

        except Exception as e:
            logger.error("build_research_profile(%s) failed: %s", sl(user_id), sl(e))
            return None

    async def run_research_cycle(self, user_id: str) -> Optional[ResearchReport]:
        """
        Execute a full research cycle:
        1. Build profile
        2. Generate search queries
        3. Execute searches
        4. Fetch & score top results
        5. Store findings
        6. Return report
        """
        try:
            # Step 1: Build profile
            profile = await self.build_research_profile(user_id)
            if not profile:
                logger.error("Could not build research profile for %s", sl(user_id))
                return None

            logger.info(
                "Running research cycle for %s (%s)",
                profile.company_name,
                profile.industry,
            )

            # Step 2: Generate queries
            all_queries = await self._generate_queries(profile)
            logger.info("Generated %d queries for research", len(all_queries))

            competitor_updates = []
            trends = []
            customer_signals = []
            findings_stored = 0
            pages_crawled = 0

            # Step 3 & 4: Execute searches and fetch results
            for category, queries in all_queries.items():
                for query in queries:
                    try:
                        results = await self.crawl_engine.search_web(
                            query, num_results=5
                        )
                        pages_crawled += len(results)

                        for result in results:
                            # Score relevance
                            relevance = await self._score_relevance(
                                f"{result.title}\n{result.snippet}", profile
                            )

                            if relevance < 0.3:
                                # Skip low-relevance results
                                continue

                            # Categorize finding
                            if category == "competitor":
                                update = CompetitorUpdate(
                                    competitor=self._infer_competitor(result.title),
                                    title=result.title,
                                    summary=result.snippet,
                                    source_url=result.url,
                                    change_type=self._infer_change_type(
                                        result.title
                                    ),
                                )
                                competitor_updates.append(update)

                            elif category == "trend":
                                trend = TrendItem(
                                    topic=query,
                                    summary=result.snippet,
                                    sources=[result.url],
                                    relevance=relevance,
                                )
                                trends.append(trend)

                            elif category == "customer":
                                signal = CustomerSignal(
                                    topic=query,
                                    sentiment=self._infer_sentiment(result.snippet),
                                    summary=result.snippet,
                                    source_url=result.url,
                                    platform=self._infer_platform(result.url),
                                )
                                customer_signals.append(signal)

                            # Step 5: Store finding
                            finding = ResearchFinding(
                                title=result.title,
                                content=result.snippet,
                                source_url=result.url,
                                category=category,
                                relevance_score=relevance,
                                tags=list(profile.keywords)[:5],
                            )

                            finding_id = await self._store_finding(user_id, finding)
                            if finding_id:
                                findings_stored += 1

                    except Exception as e:
                        logger.error(
                            "Error processing query '%s' for %s: %s",
                            sl(query),
                            sl(user_id),
                            sl(e),
                        )

            report = ResearchReport(
                user_id=user_id,
                generated_at=datetime.now(timezone.utc),
                competitor_updates=competitor_updates,
                trends=trends,
                customer_signals=customer_signals,
                findings_stored=findings_stored,
                queries_executed=len(all_queries.get("competitor", [])) + len(
                    all_queries.get("trend", [])
                ) + len(all_queries.get("customer", [])),
                pages_crawled=pages_crawled,
            )

            logger.info(
                "Research cycle complete: %d findings stored, %d pages crawled",
                findings_stored,
                pages_crawled,
            )

            return report

        except Exception as e:
            logger.error("run_research_cycle(%s) failed: %s", sl(user_id), sl(e))
            return None

    async def monitor_competitors(
        self, user_id: str, competitors: list[str]
    ) -> list[CompetitorUpdate]:
        """Check competitor websites and news for changes."""
        updates = []

        try:
            for competitor in competitors:
                queries = [
                    f"{competitor} news latest",
                    f"{competitor} product update",
                    f"{competitor} funding",
                ]

                for query in queries:
                    try:
                        results = await self.crawl_engine.search_web(
                            query, num_results=3
                        )

                        for result in results:
                            update = CompetitorUpdate(
                                competitor=competitor,
                                title=result.title,
                                summary=result.snippet,
                                source_url=result.url,
                                change_type=self._infer_change_type(result.title),
                            )
                            updates.append(update)

                    except Exception as e:
                        logger.error(
                            "Error monitoring competitor %s: %s", competitor, e
                        )

        except Exception as e:
            logger.error("monitor_competitors failed: %s", e)

        return updates

    async def track_industry_trends(
        self, user_id: str, industry: str
    ) -> list[TrendItem]:
        """Search for industry trends, new tech, market shifts."""
        trends = []

        try:
            profile = await self.build_research_profile(user_id)
            if not profile:
                return trends

            queries = get_trend_search_queries(
                industry, profile.technologies, profile.keywords
            )

            for query in queries[:5]:  # Limit to avoid overload
                try:
                    results = await self.crawl_engine.search_web(
                        query, num_results=3
                    )

                    for result in results:
                        relevance = await self._score_relevance(
                            f"{result.title}\n{result.snippet}", profile
                        )

                        trend = TrendItem(
                            topic=query,
                            summary=result.snippet,
                            sources=[result.url],
                            relevance=relevance,
                        )
                        trends.append(trend)

                except Exception as e:
                    logger.error("Error tracking trend '%s': %s", query, e)

        except Exception as e:
            logger.error("track_industry_trends failed: %s", e)

        return trends

    async def gather_customer_signals(self, user_id: str) -> list[CustomerSignal]:
        """Search for customer pain points, reviews, forum discussions."""
        signals = []

        try:
            profile = await self.build_research_profile(user_id)
            if not profile:
                return signals

            queries = get_customer_signal_queries(
                profile.company_name, profile.industry, profile.target_audience
            )

            for query in queries[:5]:  # Limit
                try:
                    results = await self.crawl_engine.search_web(
                        query, num_results=3
                    )

                    for result in results:
                        signal = CustomerSignal(
                            topic=query,
                            sentiment=self._infer_sentiment(result.snippet),
                            summary=result.snippet,
                            source_url=result.url,
                            platform=self._infer_platform(result.url),
                        )
                        signals.append(signal)

                except Exception as e:
                    logger.error("Error gathering signal '%s': %s", query, e)

        except Exception as e:
            logger.error("gather_customer_signals failed: %s", e)

        return signals

    # ────────────────────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────────────────────

    async def _generate_queries(self, profile: ResearchProfile) -> dict[str, list[str]]:
        """Generate smart search queries from founder's context."""
        queries = {
            "competitor": get_competitor_search_queries(
                profile.competitors, profile.industry
            )
            if profile.competitors
            else [],
            "trend": get_trend_search_queries(
                profile.industry, profile.technologies, profile.keywords
            ),
            "customer": get_customer_signal_queries(
                profile.company_name, profile.industry, profile.target_audience
            ),
        }

        # Filter to remove None/empty
        return {
            k: [q for q in v if q and q.strip()] for k, v in queries.items()
        }

    async def _score_relevance(self, text: str, profile: ResearchProfile) -> float:
        """
        Score relevance of text to founder's profile (0-1).
        Uses keyword matching + simple TF-like scoring.
        """
        if not text:
            return 0.0

        text_lower = text.lower()
        score = 0.0

        # Keywords
        for keyword in profile.keywords:
            if keyword.lower() in text_lower:
                score += 0.2

        # Company name
        if profile.company_name.lower() in text_lower:
            score += 0.3

        # Industry
        if profile.industry.lower() in text_lower:
            score += 0.2

        # Competitors
        for competitor in profile.competitors:
            if competitor.lower() in text_lower:
                score += 0.25

        # Target audience
        if profile.target_audience.lower() in text_lower:
            score += 0.15

        # Recent topics
        for topic in profile.recent_topics[:3]:
            if topic.lower() in text_lower:
                score += 0.1

        return min(score, 1.0)  # Cap at 1.0

    async def _store_finding(
        self, user_id: str, finding: ResearchFinding
    ) -> Optional[uuid.UUID]:
        """Store a research finding as memory_page."""
        try:
            memory_manager = get_memory_manager()

            # Store via memory manager
            page_id = await memory_manager.async_store(
                user_id=user_id,
                title=finding.title,
                content=finding.content,
                page_type="insight",
                importance=finding.relevance_score,
                decay_rate=0.01,  # Fade faster than user memories
                chapter="research",
                tags=finding.tags,
                entities=finding.entities,
                summary=f"Research finding: {finding.category}",
                source="crawler",
                metadata={
                    "source_url": finding.source_url,
                    "category": finding.category,
                    "relevance_score": finding.relevance_score,
                },
                auto_embed=True,
            )

            logger.debug("Stored research finding %s for %s", page_id, sl(user_id))
            return page_id

        except Exception as e:
            logger.error("_store_finding failed: %s", e)
            return None

    def _infer_competitor(self, title: str) -> str:
        """Try to extract competitor name from title."""
        # Simple heuristic: take first capitalized word or phrase
        parts = title.split()
        for part in parts:
            if part[0].isupper() and len(part) > 2:
                return part.strip(".,!?")
        return "Unknown"

    def _infer_change_type(self, title: str) -> str:
        """Infer what type of change based on title."""
        title_lower = title.lower()

        if "launch" in title_lower or "release" in title_lower:
            return "product_launch"
        elif "price" in title_lower or "pricing" in title_lower:
            return "pricing"
        elif "fund" in title_lower or "invest" in title_lower:
            return "funding"
        elif "hire" in title_lower or "hiring" in title_lower or "job" in title_lower:
            return "hiring"
        else:
            return "news"

    def _infer_sentiment(self, text: str) -> str:
        """Infer sentiment from text snippet."""
        text_lower = text.lower()

        positive_words = [
            "great",
            "amazing",
            "excellent",
            "love",
            "best",
            "innovative",
            "success",
        ]
        negative_words = [
            "bad",
            "terrible",
            "horrible",
            "hate",
            "worst",
            "issue",
            "problem",
            "fail",
        ]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        else:
            return "neutral"

    def _infer_platform(self, url: str) -> str:
        """Infer platform from URL."""
        url_lower = url.lower()

        if "reddit.com" in url_lower:
            return "reddit"
        elif "twitter.com" in url_lower or "x.com" in url_lower:
            return "twitter"
        elif "producthunt.com" in url_lower:
            return "producthunt"
        elif "g2.com" in url_lower:
            return "g2"
        elif "trustpilot.com" in url_lower:
            return "trustpilot"
        else:
            return "forum"


# ============================================================================
# Singleton factory
# ============================================================================

_research_engine_instance: Optional[ResearchEngine] = None


def get_research_engine(crawl_engine: Optional[CrawlEngine] = None) -> ResearchEngine:
    """Get or create singleton ResearchEngine."""
    global _research_engine_instance
    if _research_engine_instance is None:
        if crawl_engine is None:
            from app.crawler.engine import get_crawler_engine
            crawl_engine = get_crawler_engine()
        _research_engine_instance = ResearchEngine(crawl_engine)
    return _research_engine_instance
