"""
Founder OS — Web Crawler & Research Engine
============================================
Automated web research for solopreneurs.

Reads founder business context from the database (planner_users, memory_pages)
and automatically crawls the web for:
  - Competitor updates
  - Industry trends
  - Technology changes
  - Customer sentiment
  - Relevant news

Public API:
  - CrawlEngine          — Core HTTP crawler with rate limiting & HTML extraction
  - ResearchEngine       — Orchestrates research cycles tied to founder context
  - get_crawler_engine() — Singleton factory for CrawlEngine
"""

from __future__ import annotations

from app.crawler.engine import CrawlEngine, CrawlResult, FeedItem, SearchResult
from app.crawler.research import (
    ResearchEngine,
    ResearchProfile,
    ResearchFinding,
    CompetitorUpdate,
    TrendItem,
    CustomerSignal,
    ResearchReport,
)

__all__ = [
    "CrawlEngine",
    "CrawlResult",
    "FeedItem",
    "SearchResult",
    "ResearchEngine",
    "ResearchProfile",
    "ResearchFinding",
    "CompetitorUpdate",
    "TrendItem",
    "CustomerSignal",
    "ResearchReport",
]
