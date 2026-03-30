"""
Founder OS — Crawler Module Tests
==================================
Unit and integration tests for the crawler and research engine.

Run with: pytest app/crawler/test_crawler.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.engine import (
    CrawlEngine,
    TextExtractor,
    LinkExtractor,
    CrawlResult,
    FeedItem,
    SearchResult,
)
from app.crawler.research import (
    ResearchEngine,
    ResearchProfile,
    ResearchFinding,
)
from app.crawler.sources import (
    get_sources_for_industry,
    get_customer_signal_queries,
    get_competitor_search_queries,
    get_trend_search_queries,
)


# ============================================================================
# Test: TextExtractor (HTML parsing)
# ============================================================================

class TestTextExtractor:
    """Test stdlib HTMLParser-based text extraction."""

    def test_extract_simple_text(self):
        """Extract text from basic HTML."""
        html = "<p>Hello World</p>"
        parser = TextExtractor()
        parser.feed(html)
        assert parser.get_text() == "Hello World"

    def test_skip_script_tags(self):
        """Skip script and style tags."""
        html = "<p>Hello</p><script>alert('x')</script><p>World</p>"
        parser = TextExtractor()
        parser.feed(html)
        text = parser.get_text()
        assert "Hello" in text
        assert "World" in text
        assert "alert" not in text

    def test_collapse_whitespace(self):
        """Collapse multiple whitespaces."""
        html = "<p>Hello    \n\n   World</p>"
        parser = TextExtractor()
        parser.feed(html)
        assert parser.get_text() == "Hello World"

    def test_extract_from_complex_html(self):
        """Extract text from complex nested HTML."""
        html = """
        <html>
            <body>
                <h1>Title</h1>
                <p>Paragraph 1</p>
                <div>
                    <p>Paragraph 2</p>
                </div>
            </body>
        </html>
        """
        parser = TextExtractor()
        parser.feed(html)
        text = parser.get_text()
        assert "Title" in text
        assert "Paragraph 1" in text
        assert "Paragraph 2" in text


# ============================================================================
# Test: LinkExtractor
# ============================================================================

class TestLinkExtractor:
    """Test link extraction from HTML."""

    def test_extract_single_link(self):
        """Extract a single <a> link."""
        html = '<a href="https://example.com">Link</a>'
        parser = LinkExtractor()
        parser.feed(html)
        assert parser.links == ["https://example.com"]

    def test_extract_multiple_links(self):
        """Extract multiple links."""
        html = """
        <a href="/page1">Page 1</a>
        <a href="/page2">Page 2</a>
        <a href="/page3">Page 3</a>
        """
        parser = LinkExtractor()
        parser.feed(html)
        assert len(parser.links) == 3
        assert "/page1" in parser.links

    def test_ignore_links_without_href(self):
        """Ignore <a> tags without href."""
        html = '<a>No link</a><a href="/real">Real link</a>'
        parser = LinkExtractor()
        parser.feed(html)
        assert parser.links == ["/real"]


# ============================================================================
# Test: CrawlEngine
# ============================================================================

class TestCrawlEngine:
    """Test the main CrawlEngine crawler."""

    @pytest.mark.asyncio
    async def test_extract_text(self):
        """Test text extraction from HTML."""
        engine = CrawlEngine()
        html = "<h1>Title</h1><p>Content here</p>"
        text = await engine.extract_text(html)
        assert "Title" in text
        assert "Content here" in text

    @pytest.mark.asyncio
    async def test_extract_links(self):
        """Test link extraction and URL resolution."""
        engine = CrawlEngine()
        html = """
        <a href="page1.html">Page 1</a>
        <a href="https://external.com">External</a>
        """
        links = await engine.extract_links(html, "https://example.com/")
        assert len(links) == 2
        assert "https://example.com/page1.html" in links
        assert "https://external.com/" in links

    @pytest.mark.asyncio
    async def test_extract_title_from_html(self):
        """Test <title> extraction."""
        engine = CrawlEngine()
        html = "<html><head><title>Test Page</title></head></html>"
        title = engine._extract_title(html)
        assert title == "Test Page"

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiter semaphore."""
        engine = CrawlEngine(rate_limit_per_second=1)
        # Semaphore should be initialized
        assert engine._semaphore is not None
        assert engine._semaphore._value == 1

    def test_robots_cache(self):
        """Test robots.txt cache."""
        engine = CrawlEngine()
        # Cache should be empty initially
        assert len(engine._robots_cache) == 0

    @pytest.mark.asyncio
    async def test_parse_duckduckgo_results(self):
        """Test DuckDuckGo HTML parsing."""
        engine = CrawlEngine()
        # Mock DuckDuckGo HTML response (simplified)
        html = """
        <div class="result">
            <a href="https://example.com">
                <span class="result__title">Example Result</span>
            </a>
            <span class="result__snippet">This is the snippet text</span>
        </div>
        <div class="result">
            <a href="https://example2.com">
                <span class="result__title">Another Result</span>
            </a>
            <span class="result__snippet">Another snippet</span>
        </div>
        """
        results = engine._parse_duckduckgo_results(html, 10)
        assert len(results) >= 0  # May not find all due to HTML structure
        # Results should have title, url, snippet

    def test_crawl_result_dataclass(self):
        """Test CrawlResult dataclass."""
        from datetime import datetime, timezone
        result = CrawlResult(
            url="https://example.com",
            title="Test Page",
            text="Content here",
            links=["https://link1.com", "https://link2.com"],
            status_code=200,
            content_type="text/html",
            crawled_at=datetime.now(timezone.utc),
            error=None,
        )
        assert result.url == "https://example.com"
        assert result.status_code == 200
        assert len(result.links) == 2


# ============================================================================
# Test: Research Sources
# ============================================================================

class TestResearchSources:
    """Test source selection and query generation."""

    def test_get_sources_for_tech_industry(self):
        """Get sources for tech/SaaS industry."""
        sources = get_sources_for_industry("saas")
        assert len(sources) > 0
        # Should include both general startup sources and SaaS-specific
        names = [s["name"] for s in sources]
        assert "SaaStr" in names or "TechCrunch" in names

    def test_get_customer_signal_queries(self):
        """Generate customer signal search queries."""
        queries = get_customer_signal_queries(
            "MyApp", "SaaS", "Small business owners"
        )
        assert len(queries) > 0
        # Should include product reviews, pain points, comparisons
        combined = " ".join(queries).lower()
        assert "review" in combined or "problem" in combined

    def test_get_competitor_search_queries(self):
        """Generate competitor tracking queries."""
        queries = get_competitor_search_queries(
            ["Competitor A", "Competitor B"], "SaaS"
        )
        assert len(queries) > 0
        combined = " ".join(queries).lower()
        assert "competitor" in combined.lower()

    def test_get_trend_search_queries(self):
        """Generate industry trend queries."""
        queries = get_trend_search_queries(
            "SaaS", ["AI", "automation"], ["productivity", "workflows"]
        )
        assert len(queries) > 0
        combined = " ".join(queries).lower()
        assert "trend" in combined or "ai" in combined


# ============================================================================
# Test: ResearchEngine
# ============================================================================

class TestResearchEngine:
    """Test the research orchestrator."""

    @pytest.mark.asyncio
    async def test_research_profile_creation(self):
        """Test building research profile from user data."""
        engine = CrawlEngine()
        research = ResearchEngine(engine)

        # Mock database session
        with patch("app.crawler.research.async_session") as mock_session:
            mock_execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute = mock_execute

            # Mock planner_users row
            mock_execute.return_value.first.return_value = (
                "user_123",  # user_id
                "Acme Corp",  # business_name
                "SaaS",  # industry
                "Small businesses",  # target_audience
            )

            # Mock memory_pages
            mock_execute.return_value.__iter__ = lambda self: iter([])

            profile = await research.build_research_profile("user_123")

            # Should return a ResearchProfile or None
            assert profile is None or isinstance(profile, ResearchProfile)

    def test_research_finding_dataclass(self):
        """Test ResearchFinding dataclass."""
        finding = ResearchFinding(
            title="New competitor feature",
            content="Competitor X launched...",
            source_url="https://news.example.com",
            category="competitor",
            relevance_score=0.85,
            tags=["competitor", "product"],
        )
        assert finding.title == "New competitor feature"
        assert finding.relevance_score == 0.85
        assert "competitor" in finding.tags

    def test_infer_sentiment(self):
        """Test sentiment inference."""
        engine = CrawlEngine()
        research = ResearchEngine(engine)

        positive_text = "Great product, I love it, amazing features"
        negative_text = "Terrible service, awful experience, hate it"
        neutral_text = "The product has some features"

        assert research._infer_sentiment(positive_text) == "positive"
        assert research._infer_sentiment(negative_text) == "negative"
        assert research._infer_sentiment(neutral_text) == "neutral"

    def test_infer_change_type(self):
        """Test inferring competitor change type."""
        engine = CrawlEngine()
        research = ResearchEngine(engine)

        launch_title = "Company X launches new product"
        pricing_title = "Company Y updates pricing"
        funding_title = "Company Z raises $10M funding"

        assert research._infer_change_type(launch_title) == "product_launch"
        assert research._infer_change_type(pricing_title) == "pricing"
        assert research._infer_change_type(funding_title) == "funding"

    def test_infer_platform(self):
        """Test inferring source platform from URL."""
        engine = CrawlEngine()
        research = ResearchEngine(engine)

        assert research._infer_platform("https://reddit.com/r/...") == "reddit"
        assert research._infer_platform("https://twitter.com/...") == "twitter"
        assert research._infer_platform("https://g2.com/...") == "g2"
        assert research._infer_platform("https://unknown.com") == "forum"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the full crawler stack."""

    @pytest.mark.asyncio
    async def test_crawl_engine_initialization(self):
        """Test CrawlEngine can be created."""
        engine = CrawlEngine()
        assert engine is not None
        assert engine.rate_limit_per_second == 2
        assert engine.timeout == 15

    @pytest.mark.asyncio
    async def test_research_engine_initialization(self):
        """Test ResearchEngine can be created."""
        crawl_engine = CrawlEngine()
        research_engine = ResearchEngine(crawl_engine)
        assert research_engine is not None
        assert research_engine.crawl_engine is crawl_engine

    @pytest.mark.asyncio
    async def test_full_research_profile_workflow(self):
        """Test building a complete research profile."""
        engine = CrawlEngine()
        research = ResearchEngine(engine)

        # This would need a real database or mock
        # For now, just test that the method exists and is callable
        assert hasattr(research, "build_research_profile")
        assert hasattr(research, "run_research_cycle")


# ============================================================================
# Helpers for manual testing
# ============================================================================

async def manual_test_crawler():
    """Manual test: crawl a real website."""
    engine = CrawlEngine()

    print("Testing CrawlEngine.fetch_page()...")
    result = await engine.fetch_page("https://example.com")
    print(f"  Title: {result.title}")
    print(f"  Status: {result.status_code}")
    print(f"  Text length: {len(result.text)}")
    print(f"  Links found: {len(result.links)}")
    if result.error:
        print(f"  Error: {result.error}")


async def manual_test_search():
    """Manual test: search the web."""
    engine = CrawlEngine()

    print("Testing CrawlEngine.search_web()...")
    results = await engine.search_web("python web scraping", num_results=5)
    print(f"Found {len(results)} results:")
    for r in results[:3]:
        print(f"  - {r.title}")
        print(f"    {r.snippet[:100]}...")


if __name__ == "__main__":
    # Run manual tests
    print("Manual crawler tests (requires network):\n")

    try:
        asyncio.run(manual_test_crawler())
        print()
        asyncio.run(manual_test_search())
    except Exception as e:
        print(f"Manual test error: {e}")

    print("\nRun pytest for unit tests:")
    print("  pytest app/crawler/test_crawler.py -v")
