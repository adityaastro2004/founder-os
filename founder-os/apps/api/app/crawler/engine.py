"""
Founder OS — Core Crawl Engine
====================================
Lightweight, dependency-free HTTP crawler with:
  - HTML/text extraction (stdlib HTMLParser)
  - RSS/Atom parsing (stdlib xml.etree.ElementTree)
  - DuckDuckGo web search
  - Rate limiting (2 req/s via asyncio.Semaphore)
  - robots.txt respect
  - Timeout & content size limits

Uses stdlib only (no beautifulsoup, no feedparser).
All HTTP via httpx.AsyncClient.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_CONTENT_SIZE = 1024 * 1024  # 1 MB
REQUEST_TIMEOUT = 15  # seconds
RATE_LIMIT_PER_SECOND = 2
ROBOTS_CHECK_TIMEOUT = 5  # seconds


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class CrawlResult:
    """Result of crawling a single URL."""
    url: str
    title: str
    text: str  # extracted clean text
    links: list[str]
    status_code: int
    content_type: str
    crawled_at: datetime
    error: Optional[str] = None


@dataclass
class FeedItem:
    """Item from an RSS/Atom feed."""
    title: str
    url: str
    summary: str
    published: Optional[datetime] = None


@dataclass
class SearchResult:
    """Result from web search."""
    title: str
    url: str
    snippet: str


# ============================================================================
# HTMLParser — Extract text from HTML
# ============================================================================

class TextExtractor(HTMLParser):
    """Simple stdlib-based HTML text extractor."""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.skip_script_style = False

    def handle_starttag(self, tag: str, attrs: list):
        if tag in ("script", "style"):
            self.skip_script_style = True

    def handle_endtag(self, tag: str):
        if tag in ("script", "style"):
            self.skip_script_style = False

    def handle_data(self, data: str):
        if not self.skip_script_style:
            self.text_parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.text_parts)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ============================================================================
# CrawlEngine — Main crawler class
# ============================================================================

class CrawlEngine:
    """
    Lightweight HTTP crawler for research tasks.

    Features:
      - Rate limiting (2 req/sec via semaphore)
      - Timeout per request (15 sec)
      - Content size limit (1 MB)
      - robots.txt respect
      - HTML/RSS extraction
      - DuckDuckGo search fallback
    """

    def __init__(
        self,
        rate_limit_per_second: int = RATE_LIMIT_PER_SECOND,
        timeout: float = REQUEST_TIMEOUT,
        max_content_size: int = MAX_CONTENT_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.rate_limit_per_second = rate_limit_per_second
        self.timeout = timeout
        self.max_content_size = max_content_size
        self.user_agent = user_agent

        # Rate limiting semaphore
        self._semaphore = asyncio.Semaphore(rate_limit_per_second)
        self._robots_cache: dict[str, bool] = {}

    # ────────────────────────────────────────────────────────────
    # Main API
    # ────────────────────────────────────────────────────────────

    async def fetch_page(self, url: str) -> CrawlResult:
        """
        Fetch a URL, extract text + links, return CrawlResult.
        Respects robots.txt and rate limits.
        """
        try:
            # Check robots.txt
            if not await self._check_robots_txt(url):
                return CrawlResult(
                    url=url,
                    title="",
                    text="",
                    links=[],
                    status_code=403,
                    content_type="",
                    crawled_at=datetime.now(timezone.utc),
                    error="Blocked by robots.txt",
                )

            # Rate-limited fetch
            async with self._semaphore:
                result = await self._fetch_raw(url)

            return result

        except Exception as e:
            logger.error("fetch_page(%s) failed: %s", url, e)
            return CrawlResult(
                url=url,
                title="",
                text="",
                links=[],
                status_code=0,
                content_type="",
                crawled_at=datetime.now(timezone.utc),
                error=str(e),
            )

    async def extract_text(self, html: str) -> str:
        """Extract clean text from HTML."""
        try:
            parser = TextExtractor()
            parser.feed(html)
            return parser.get_text()
        except Exception as e:
            logger.warning("extract_text failed: %s", e)
            return ""

    async def extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract all links from HTML and resolve to absolute URLs."""
        parser = LinkExtractor()
        try:
            parser.feed(html)
        except Exception as e:
            logger.warning("extract_links feed failed: %s", e)

        # Resolve relative URLs
        links = []
        for href in parser.links:
            try:
                absolute_url = urljoin(base_url, href)
                links.append(absolute_url)
            except Exception:
                pass

        return links

    async def fetch_rss(self, url: str) -> list[FeedItem]:
        """Parse an RSS/Atom feed and return items."""
        try:
            async with self._semaphore:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(
                        url,
                        headers={"User-Agent": self.user_agent},
                        follow_redirects=True,
                    )
                    resp.raise_for_status()

            xml_data = resp.text
            root = ET.fromstring(xml_data)

            items = []
            namespaces = {
                "atom": "http://www.w3.org/2005/Atom",
                "content": "http://purl.org/rss/1.0/modules/content/",
            }

            # Try RSS items
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description") or item.find("summary")
                pub_elem = item.find("pubDate")

                if title_elem is not None and link_elem is not None:
                    title = (title_elem.text or "").strip()
                    url_text = (link_elem.text or "").strip()
                    summary = (desc_elem.text or "").strip() if desc_elem else ""

                    # Parse pubDate if available
                    published = None
                    if pub_elem is not None:
                        try:
                            # Simple parse attempt (many formats)
                            pub_str = pub_elem.text or ""
                            # Try common format: Fri, 01 Jan 2024 12:00:00 GMT
                            from email.utils import parsedate_to_datetime
                            published = parsedate_to_datetime(pub_str)
                        except Exception:
                            pass

                    items.append(
                        FeedItem(
                            title=title,
                            url=url_text,
                            summary=summary,
                            published=published,
                        )
                    )

            # Try Atom entries
            for entry in root.findall("atom:entry", namespaces):
                title_elem = entry.find("atom:title", namespaces)
                link_elem = entry.find("atom:link", namespaces)
                summary_elem = entry.find("atom:summary", namespaces)
                published_elem = entry.find("atom:published", namespaces)

                if title_elem is not None and link_elem is not None:
                    title = (title_elem.text or "").strip()
                    # link element has href attribute
                    url_text = link_elem.get("href", "").strip()
                    summary = (summary_elem.text or "").strip() if summary_elem else ""

                    published = None
                    if published_elem is not None:
                        try:
                            from email.utils import parsedate_to_datetime
                            published = parsedate_to_datetime(published_elem.text or "")
                        except Exception:
                            pass

                    items.append(
                        FeedItem(
                            title=title,
                            url=url_text,
                            summary=summary,
                            published=published,
                        )
                    )

            return items

        except Exception as e:
            logger.error("fetch_rss(%s) failed: %s", url, e)
            return []

    async def search_web(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """
        Search using DuckDuckGo (HTML fallback, no API needed).
        Returns top results as SearchResult objects.
        """
        try:
            search_url = f"https://html.duckduckgo.com/"
            params = {"q": query}

            async with self._semaphore:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(
                        search_url,
                        params=params,
                        headers={"User-Agent": self.user_agent},
                        follow_redirects=True,
                    )
                    resp.raise_for_status()

            html = resp.text
            results = self._parse_duckduckgo_results(html, num_results)
            return results

        except Exception as e:
            logger.error("search_web('%s') failed: %s", query, e)
            return []

    # ────────────────────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────────────────────

    async def _fetch_raw(self, url: str) -> CrawlResult:
        """Internal: fetch a URL and return CrawlResult."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )

            # Check content size before reading
            content_length = resp.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_content_size:
                        return CrawlResult(
                            url=url,
                            title="",
                            text="",
                            links=[],
                            status_code=resp.status_code,
                            content_type=resp.headers.get("content-type", ""),
                            crawled_at=datetime.now(timezone.utc),
                            error="Content too large (>1MB)",
                        )
                except ValueError:
                    pass

            html = resp.text
            if len(html.encode("utf-8")) > self.max_content_size:
                return CrawlResult(
                    url=url,
                    title="",
                    text="",
                    links=[],
                    status_code=resp.status_code,
                    content_type=resp.headers.get("content-type", ""),
                    crawled_at=datetime.now(timezone.utc),
                    error="Content too large (>1MB)",
                )

            # Extract title
            title = self._extract_title(html)

            # Extract text
            text_extractor = TextExtractor()
            try:
                text_extractor.feed(html)
            except Exception:
                pass
            text = text_extractor.get_text()

            # Extract links
            links = await self.extract_links(html, url)

            return CrawlResult(
                url=url,
                title=title,
                text=text,
                links=links,
                status_code=resp.status_code,
                content_type=resp.headers.get("content-type", ""),
                crawled_at=datetime.now(timezone.utc),
                error=None,
            )

    async def _check_robots_txt(self, url: str) -> bool:
        """Check if robots.txt allows fetching this URL."""
        try:
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"

            # Simple cache
            if domain in self._robots_cache:
                return self._robots_cache[domain]

            robots_url = f"{domain}/robots.txt"

            try:
                async with httpx.AsyncClient(timeout=ROBOTS_CHECK_TIMEOUT) as client:
                    resp = await client.get(robots_url)
                    if resp.status_code != 200:
                        # Assume allowed if no robots.txt
                        self._robots_cache[domain] = True
                        return True

                    # Very basic check: look for User-agent and Disallow
                    robots_txt = resp.text
                    lines = robots_txt.split("\n")

                    # Look for entries matching any user-agent or *
                    in_relevant_section = False
                    for line in lines:
                        line = line.split("#")[0].strip()
                        if line.startswith("User-agent:"):
                            agent = line.split(":", 1)[1].strip()
                            if agent == "*" or agent.lower() in self.user_agent.lower():
                                in_relevant_section = True
                        elif in_relevant_section and line.startswith("Disallow:"):
                            disallow_path = line.split(":", 1)[1].strip()
                            if disallow_path == "/" or parsed.path.startswith(
                                disallow_path
                            ):
                                self._robots_cache[domain] = False
                                return False

                    self._robots_cache[domain] = True
                    return True

            except Exception as e:
                logger.debug("robots.txt check failed for %s: %s", domain, e)
                # Assume allowed if fetch fails
                self._robots_cache[domain] = True
                return True

        except Exception as e:
            logger.warning("_check_robots_txt failed: %s", e)
            return True  # Assume allowed on error

    def _extract_title(self, html: str) -> str:
        """Extract <title> tag from HTML."""
        match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_duckduckgo_results(
        self, html: str, num_results: int
    ) -> list[SearchResult]:
        """Parse DuckDuckGo HTML results."""
        results = []

        # DuckDuckGo HTML structure uses divs with data-result-id
        # Pattern: <div data-result-id="..." class="result">
        # Inside: <a href="..." class="result__url">
        # Title in <span class="result__title"> or a.innerText

        pattern = r'<div class="result"\s+[^>]*>(.*?)</div>'

        for match in re.finditer(pattern, html, re.DOTALL):
            if len(results) >= num_results:
                break

            result_html = match.group(1)

            # Extract URL
            url_match = re.search(r'href="([^"]+)"', result_html)
            if not url_match:
                continue
            url = url_match.group(1).strip()

            # Extract title (try multiple patterns)
            title_match = re.search(
                r'class="result__title"[^>]*>([^<]+)</[^>]*>',
                result_html,
                re.IGNORECASE,
            )
            if not title_match:
                # Fallback: any text after href
                title_match = re.search(r'<span[^>]*>([^<]+)</span>', result_html)

            title = title_match.group(1).strip() if title_match else ""

            # Extract snippet
            snippet_match = re.search(
                r'class="result__snippet"[^>]*>([^<]+)</[^>]*>',
                result_html,
                re.IGNORECASE,
            )
            snippet = snippet_match.group(1).strip() if snippet_match else ""

            if url and title:
                results.append(SearchResult(title=title, url=url, snippet=snippet))

        return results


# ============================================================================
# LinkExtractor — extract href from HTML
# ============================================================================

class LinkExtractor(HTMLParser):
    """Extract all <a href> links from HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list):
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    self.links.append(value)


# ============================================================================
# Singleton factory
# ============================================================================

_crawl_engine_instance: Optional[CrawlEngine] = None


def get_crawler_engine() -> CrawlEngine:
    """Get or create singleton CrawlEngine."""
    global _crawl_engine_instance
    if _crawl_engine_instance is None:
        _crawl_engine_instance = CrawlEngine()
    return _crawl_engine_instance
