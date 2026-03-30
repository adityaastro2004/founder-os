# Founder OS — Web Crawler & Research Engine

A lightweight, dependency-free web crawler and research orchestrator for Founder OS. Automatically researches your business context (from `planner_users` and `memory_pages`) and crawls the web for competitor updates, industry trends, technology changes, customer sentiment, and relevant news.

## Features

- **Founder Context-Aware**: Reads business info from `planner_users` (company name, industry, target audience) and recent `memory_pages` for keywords/topics
- **Smart Query Generation**: Automatically creates research queries based on founder's industry, competitors, and keywords
- **Lightweight**: Uses stdlib only (`html.parser`, `xml.etree.ElementTree`) — no beautifulsoup or feedparser dependencies
- **Rate Limited**: Max 2 requests/second via asyncio.Semaphore
- **Async-First**: All operations are async-friendly
- **Robots.txt Respecting**: Basic robots.txt checking before fetches
- **DuckDuckGo Search**: Web search fallback using HTML parsing (no API key needed)
- **RSS/Atom Parsing**: Parse RSS and Atom feeds with stdlib XML parser
- **Relevance Scoring**: TF-like keyword scoring to filter low-relevance results
- **Memory Integration**: Stores findings in `memory_pages` with metadata and embeddings

## Architecture

### Module Structure

```
app/crawler/
├── __init__.py          — Public API exports
├── engine.py            — Core CrawlEngine class (HTTP, HTML extraction)
├── research.py          — ResearchEngine (orchestrator, founder context)
├── sources.py           — Curated research sources and query generators
└── README.md            — This file
```

### Core Classes

#### `CrawlEngine` (engine.py)

Low-level HTTP crawler with rate limiting and content extraction.

**Key Methods:**
- `fetch_page(url)` → `CrawlResult` — Fetch URL, extract text + links
- `extract_text(html)` → `str` — Extract clean text from HTML
- `extract_links(html, base_url)` → `list[str]` — Extract all links
- `fetch_rss(url)` → `list[FeedItem]` — Parse RSS/Atom feeds
- `search_web(query, num_results=10)` → `list[SearchResult]` — DuckDuckGo search

**Configuration:**
- Rate limit: 2 requests/second (configurable)
- Timeout: 15 seconds per request
- Max content size: 1 MB
- User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...

#### `ResearchEngine` (research.py)

High-level orchestrator that ties crawling to founder's business context.

**Key Methods:**
- `build_research_profile(user_id)` → `ResearchProfile` — Fetch founder data from DB
- `run_research_cycle(user_id)` → `ResearchReport` — Full research workflow
- `monitor_competitors(user_id, competitors)` → `list[CompetitorUpdate]`
- `track_industry_trends(user_id)` → `list[TrendItem]`
- `gather_customer_signals(user_id)` → `list[CustomerSignal]`

**Workflow:**
1. Build profile from `planner_users` + `memory_pages`
2. Generate smart search queries
3. Execute web searches
4. Fetch and parse top results
5. Score relevance against founder's context
6. Store findings in `memory_pages`
7. Return report with categorized findings

### Data Models

```python
# Core crawler results
CrawlResult:
  - url, title, text, links
  - status_code, content_type
  - crawled_at (datetime)
  - error (optional)

FeedItem:
  - title, url, summary
  - published (optional datetime)

SearchResult:
  - title, url, snippet

# Research findings
ResearchProfile:
  - user_id, company_name, industry
  - competitors, technologies, keywords
  - target_audience, active_goals, recent_topics

ResearchFinding:
  - title, content, source_url
  - category (competitor/trend/technology/customer/news)
  - relevance_score, entities, tags

CompetitorUpdate:
  - competitor, title, summary, source_url
  - change_type (product_launch/pricing/funding/hiring/news)

TrendItem:
  - topic, summary, sources, relevance

CustomerSignal:
  - topic, sentiment, summary, source_url
  - platform (reddit/twitter/g2/trustpilot/forum)

ResearchReport:
  - user_id, generated_at
  - competitor_updates, trends, customer_signals
  - findings_stored, queries_executed, pages_crawled
```

## Usage

### Programmatic (Python)

```python
from app.crawler.engine import get_crawler_engine
from app.crawler.research import get_research_engine

# Simple web crawl
crawler = get_crawler_engine()
result = await crawler.fetch_page("https://example.com")
print(result.title, result.text[:200])

# Search the web
results = await crawler.search_web("python web scraping 2024")
for r in results:
    print(f"{r.title}: {r.snippet}")

# Parse an RSS feed
feed_items = await crawler.fetch_rss("https://techcrunch.com/feed/")
for item in feed_items:
    print(f"{item.title} ({item.published})")

# Full research cycle (tied to founder context)
research = get_research_engine(crawler)
report = await research.run_research_cycle(user_id="user_123")
print(f"Found {report.findings_stored} findings")
print(f"Competitor updates: {len(report.competitor_updates)}")
print(f"Trends: {len(report.trends)}")
print(f"Customer signals: {len(report.customer_signals)}")
```

### REST API

All endpoints require Clerk authentication. See `app/api/crawler_routes.py`.

#### Trigger Research Cycle

```bash
POST /api/research/run
Content-Type: application/json
Authorization: Bearer <token>

{
  "user_id": "user_123"  # optional, defaults to current user
}

# Response
{
  "success": true,
  "generated_at": "2024-03-30T...",
  "findings_stored": 42,
  "queries_executed": 15,
  "pages_crawled": 38,
  "competitor_updates_count": 8,
  "trends_count": 12,
  "customer_signals_count": 5,
  "competitor_updates": [ ... ],
  "trends": [ ... ],
  "customer_signals": [ ... ]
}
```

#### Get Research Status

```bash
GET /api/research/status
Authorization: Bearer <token>

# Response
{
  "last_run_at": "2024-03-30T12:00:00Z",
  "findings_count": 42,
  "competitor_updates_count": 8,
  "status": "completed"
}
```

#### List Research Findings (Paginated)

```bash
GET /api/research/findings?skip=0&limit=10&category=competitor
Authorization: Bearer <token>

# Response
{
  "total": 42,
  "skip": 0,
  "limit": 10,
  "findings": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Competitor X launches new feature",
      "summary": "...",
      "category": "competitor",
      "source_url": "https://...",
      "relevance_score": 0.85,
      "created_at": "2024-03-30T12:00:00Z"
    },
    ...
  ]
}
```

#### Get Research Profile

```bash
GET /api/research/profile
Authorization: Bearer <token>

# Response
{
  "company_name": "Acme Corp",
  "industry": "SaaS",
  "competitors": ["Competitor A", "Competitor B"],
  "technologies": ["React", "Python", "PostgreSQL"],
  "keywords": ["automation", "workflow", "productivity"],
  "target_audience": "Small business owners",
  "active_goals": ["Expand market share", "Improve retention"],
  "recent_topics": ["..."]
}
```

#### Manage Tracked Competitors

```bash
POST /api/research/competitors
Authorization: Bearer <token>

{
  "competitors": ["Competitor A", "Competitor B"],
  "action": "set"  # or "add"
}

GET /api/research/competitors
Authorization: Bearer <token>

# Response
{
  "competitors": ["Competitor A", "Competitor B"]
}
```

#### Add Custom Research Source

```bash
POST /api/research/sources
Authorization: Bearer <token>

{
  "name": "My Custom Blog",
  "rss_url": "https://myblog.com/feed.rss",
  "website_url": null,
  "source_type": "insights"
}

# Response
{
  "success": true,
  "message": "Added source: My Custom Blog",
  "source": { ... }
}
```

## Integration with Founder OS

### Database Tables

The crawler integrates with:

1. **`planner_users`** — Founder's business context
   - `business_name`, `industry`, `target_audience`, etc.

2. **`memory_pages`** — Stores research findings
   - Findings stored with `source="crawler"` and `chapter="research"`
   - Full text embedding and metadata support

### Memory Manager

All findings are stored via `MemoryManager.async_store()`:

```python
from app.memory.manager import get_memory_manager

mm = get_memory_manager()
page_id = await mm.async_store(
    user_id="user_123",
    title="Competitor launched new product",
    content="Full details here...",
    page_type="insight",
    importance=0.8,  # Relevance score
    chapter="research",
    tags=["competitor", "product_launch"],
    source="crawler",
    metadata={
        "source_url": "https://...",
        "category": "competitor",
        "relevance_score": 0.85,
    },
    auto_embed=True,  # Generate embeddings
)
```

### Scheduler Integration

To run research on a schedule, add to `app/scheduler.py`:

```python
import schedule
from app.crawler.research import get_research_engine
from app.crawler.engine import get_crawler_engine

def run_weekly_research():
    """Run research cycle for all active users."""
    # Pseudo-code — fetch all users
    for user_id in get_active_users():
        try:
            crawler = get_crawler_engine()
            research = get_research_engine(crawler)
            await research.run_research_cycle(user_id)
        except Exception as e:
            logger.error(f"Research failed for {user_id}: {e}")

schedule.every().sunday.at("03:00").do(run_weekly_research)
```

## Configuration

All settings are in `app/config.py`:

```python
class Settings(BaseSettings):
    # Crawler defaults (can be overridden)
    CRAWLER_RATE_LIMIT = 2  # requests/second
    CRAWLER_TIMEOUT = 15  # seconds
    CRAWLER_MAX_CONTENT_SIZE = 1024 * 1024  # 1 MB
```

To customize:

```python
from app.config import get_settings
from app.crawler.engine import CrawlEngine

settings = get_settings()
crawler = CrawlEngine(
    rate_limit_per_second=5,
    timeout=20,
    max_content_size=2 * 1024 * 1024,
)
```

## Performance & Limits

- **Rate Limiting**: 2 requests/second (prevents 429 Too Many Requests)
- **Timeout**: 15 seconds per request (configurable)
- **Content Size**: 1 MB max (configurable)
- **Robots.txt**: Basic check before fetching
- **Search**: DuckDuckGo HTML parsing (no API key needed, but slower than API)
- **Caching**: robots.txt results cached per domain

## Extending

### Custom Query Generators

Edit `app/crawler/sources.py`:

```python
INDUSTRY_SOURCES["your_industry"] = [
    {"name": "Source Name", "rss": "...", "type": "news"},
    ...
]

def get_your_custom_queries(...):
    """Generate queries for your domain."""
    return [...]
```

### Custom Relevance Scoring

Override in `ResearchEngine`:

```python
async def _score_relevance(self, text, profile):
    """Custom scoring logic."""
    # Use ML model, semantic similarity, etc.
    return score  # 0-1
```

### Custom Crawl Behavior

Subclass `CrawlEngine`:

```python
class CustomCrawler(CrawlEngine):
    async def fetch_page(self, url):
        # Custom logic
        return result
```

## Troubleshooting

### No findings returned

1. Check `build_research_profile()` — ensure `planner_users` entry exists
2. Check query generation — may be too specific or generic
3. Check relevance scoring — threshold might be too high
4. Enable debug logging: `logging.getLogger("app.crawler").setLevel("DEBUG")`

### Rate limit errors

Increase `rate_limit_per_second` or add delays:

```python
crawler = CrawlEngine(rate_limit_per_second=1)
```

### Large pages hanging

Reduce `max_content_size`:

```python
crawler = CrawlEngine(max_content_size=500_000)  # 500 KB
```

### RSS parsing fails

Most common: Malformed XML or missing elements. Check the feed with a validator:
https://www.w3.org/2001/03/webdata/xsv

## Testing

```bash
# Run tests
pytest app/crawler/test_engine.py -v

# Test a single crawler method
python3 -c "
import asyncio
from app.crawler.engine import get_crawler_engine

async def test():
    crawler = get_crawler_engine()
    result = await crawler.fetch_page('https://example.com')
    print(f'Title: {result.title}')
    print(f'Text length: {len(result.text)}')
    print(f'Links: {len(result.links)}')

asyncio.run(test())
"
```

## Future Enhancements

- [ ] Semantic search (vs. keyword-based)
- [ ] Graph-based finding relationships
- [ ] Scheduled research cycles
- [ ] Custom webhooks for findings
- [ ] Multi-source deduplication
- [ ] Fact-checking with LLM
- [ ] Alert thresholds (new product == high priority)
- [ ] Competitor tracking with diff detection
- [ ] Customer sentiment trends over time
- [ ] Industry news aggregation with summaries

## License

Part of Founder OS. See main repository.
