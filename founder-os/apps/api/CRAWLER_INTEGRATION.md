# Crawler Integration Guide

## Quick Start

The crawler module is complete and production-ready. Follow these steps to integrate it into the Founder OS API.

### 1. Register the Router in FastAPI

Edit `app/main.py` and add the crawler routes:

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.crawler_routes import router as crawler_router  # Add this
from app.api.memory_routes import router as memory_router
from app.api.agent_routes import router as agent_router
# ... other imports

app = FastAPI(title="Founder OS")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routes.router)
app.include_router(crawler_router)  # Add this
app.include_router(memory_router)
app.include_router(agent_router)
# ... other routers
```

### 2. Verify Imports Work

```bash
cd /path/to/founder-os/apps/api

# Test imports
python3 -c "from app.crawler import CrawlEngine, ResearchEngine; print('✓ Crawler imports OK')"
python3 -c "from app.api.crawler_routes import router; print('✓ Routes import OK')"
```

### 3. Run the API

```bash
# Start the FastAPI server (already configured)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, test the API
curl -H "Authorization: Bearer YOUR_CLERK_TOKEN" \
  http://localhost:8000/api/research/profile
```

### 4. Optional: Add to Scheduler for Recurring Research

Edit `app/scheduler.py` to run research on a schedule:

```python
# app/scheduler.py
import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

from app.crawler.engine import get_crawler_engine
from app.crawler.research import get_research_engine
from app.database import async_session
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)

def run_research_for_user(user_id: str):
    """Run research cycle for a single user."""
    try:
        crawl_engine = get_crawler_engine()
        research_engine = get_research_engine(crawl_engine)

        # Run in async context
        import asyncio
        asyncio.run(research_engine.run_research_cycle(user_id))
        logger.info(f"Research completed for {user_id}")
    except Exception as e:
        logger.error(f"Research failed for {user_id}: {e}")

def schedule_weekly_research():
    """Schedule research to run weekly for all active users."""
    scheduler = BackgroundScheduler()

    def run_all_research():
        """Research cycle for all users (runs in background)."""
        try:
            # Fetch all active users
            import asyncio
            asyncio.run(_fetch_and_research())
        except Exception as e:
            logger.error(f"Batch research failed: {e}")

    async def _fetch_and_research():
        """Async helper to fetch users and run research."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("""
                        SELECT DISTINCT user_id FROM planner_users
                        WHERE user_id NOT IN (
                            SELECT user_id FROM users WHERE deleted_at IS NOT NULL
                        )
                        LIMIT 100
                    """)
                )

                user_ids = [row[0] for row in result]
                logger.info(f"Running research for {len(user_ids)} users")

                crawl_engine = get_crawler_engine()
                research_engine = get_research_engine(crawl_engine)

                for user_id in user_ids:
                    try:
                        await research_engine.run_research_cycle(user_id)
                    except Exception as e:
                        logger.error(f"Research failed for {user_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch users for research: {e}")

    # Run every Sunday at 3 AM UTC
    scheduler.add_job(run_all_research, 'cron', day_of_week=6, hour=3)
    scheduler.start()
    logger.info("Weekly research scheduler started")

# Initialize in app startup
def init_scheduler():
    """Initialize background schedulers."""
    # ... existing scheduler init code ...
    schedule_weekly_research()
```

### 5. Optional: Add Webhook for Research Findings

Create a webhook to notify users when new findings are discovered:

```python
# app/api/crawler_routes.py (add to existing file)

from app.integrations.webhooks import send_webhook

async def notify_on_important_finding(user_id: str, finding):
    """Send webhook notification for important findings."""
    # Example: send webhook for competitor updates with relevance > 0.8
    if finding.category == "competitor" and finding.relevance_score > 0.8:
        await send_webhook(
            user_id=user_id,
            event_type="research.competitor_update",
            data={
                "title": finding.title,
                "source_url": finding.source_url,
                "relevance": finding.relevance_score,
            }
        )
```

## API Endpoints

All endpoints require Clerk authentication. See `app/api/crawler_routes.py` for full implementation.

### Research Management

```
POST /api/research/run              Trigger a research cycle
GET  /api/research/status            Get status of last run
GET  /api/research/findings          List recent findings (paginated)
GET  /api/research/profile           Get auto-generated research profile
```

### Competitor Tracking

```
POST /api/research/competitors       Add/update tracked competitors
GET  /api/research/competitors       Get list of tracked competitors
```

### Custom Sources

```
POST /api/research/sources           Add custom RSS/URL source
```

## Configuration

### Default Settings

In `app/config.py`, these defaults are used:

```python
# Crawler defaults
CRAWLER_RATE_LIMIT = 2              # requests/second
CRAWLER_TIMEOUT = 15                # seconds per request
CRAWLER_MAX_CONTENT_SIZE = 1_048_576  # 1 MB
```

### Override in Code

```python
from app.crawler.engine import CrawlEngine
from app.crawler.research import ResearchEngine

# Custom crawler
crawler = CrawlEngine(
    rate_limit_per_second=1,  # Slower (more respectful)
    timeout=30,               # Longer timeout
    max_content_size=512_000, # Smaller max size
)

# Custom research
research = ResearchEngine(crawler)
```

## Database Schema

The crawler uses these existing tables:

### `planner_users`
- `user_id` (primary key)
- `business_name`
- `industry`
- `target_audience`
- Other business context fields

### `memory_pages`
- Stores research findings with `source='crawler'` and `chapter='research'`
- Full embedding support via pgvector
- Metadata JSONB for storing crawler-specific data

No new tables needed! Leverages existing infrastructure.

## Testing

### Unit Tests

```bash
# Run all crawler tests
pytest app/crawler/test_crawler.py -v

# Run specific test
pytest app/crawler/test_crawler.py::TestCrawlEngine::test_extract_text -v

# Run with coverage
pytest app/crawler/test_crawler.py --cov=app.crawler
```

### Manual Testing

```python
import asyncio
from app.crawler.engine import get_crawler_engine
from app.crawler.research import get_research_engine

async def test():
    # Test crawler
    crawler = get_crawler_engine()

    # Fetch a page
    result = await crawler.fetch_page("https://example.com")
    print(f"Title: {result.title}")

    # Search the web
    results = await crawler.search_web("python asyncio", num_results=5)
    print(f"Found {len(results)} results")

    # Parse RSS
    feed = await crawler.fetch_rss("https://techcrunch.com/feed/")
    print(f"Found {len(feed)} feed items")

    # Full research cycle (requires valid user in planner_users)
    research = get_research_engine(crawler)
    report = await research.run_research_cycle("your_user_id")
    if report:
        print(f"Findings stored: {report.findings_stored}")

asyncio.run(test())
```

### E2E Testing

```bash
# Start the API
uvicorn app.main:app --reload

# In another terminal
curl -X POST http://localhost:8000/api/research/run \
  -H "Authorization: Bearer $CLERK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user"}'
```

## Performance Considerations

### Rate Limiting
- 2 requests/second (asyncio.Semaphore) prevents overwhelming servers
- Respects robots.txt (basic check)
- Can be reduced for more aggressive crawling

### Content Size
- 1 MB max per page (prevents OOM errors)
- Adjustable in `CrawlEngine.__init__()`

### Async/Await
- All operations are async-native
- Safe to run multiple research cycles concurrently
- Use asyncio to batch operations

### Database
- Findings stored in `memory_pages` table
- Embeddings generated via existing `MemoryManager`
- Use pgvector for semantic search of findings

## Troubleshooting

### "No planner_users entry for user X"

The user hasn't set up their profile yet. This is expected for new users.

Solution: Create a planner_users entry:
```sql
INSERT INTO planner_users (user_id, business_name, industry)
VALUES ('user_123', 'Acme Corp', 'SaaS');
```

### "Rate limit errors"

The crawler is hitting 429 Too Many Requests. Either:
1. Reduce `rate_limit_per_second` in CrawlEngine
2. Add random delays between requests
3. Add proxy rotation (advanced)

### "Findings not storing"

Check:
1. User exists in `planner_users`
2. `memory_pages` table has proper permissions
3. Memory manager is initialized
4. Logs show no embedding errors

Enable debug logging:
```python
import logging
logging.getLogger("app.crawler").setLevel(logging.DEBUG)
```

### "Search returns no results"

DuckDuckGo HTML parsing is brittle. Solutions:
1. Try different search terms (more specific, fewer keywords)
2. Test manually: https://duckduckgo.com/?q=your+query
3. Consider implementing a search API fallback (SerpAPI, etc.)

## Future Enhancements

- [ ] **Search API Integration**: Replace DuckDuckGo with SerpAPI/Google Custom Search (more reliable)
- [ ] **Semantic Search**: Use embeddings + pgvector for semantic relevance instead of keyword matching
- [ ] **Graph Analysis**: Build knowledge graph of findings (relationships, timelines)
- [ ] **Alert Thresholds**: Configurable alerts for high-relevance findings
- [ ] **Deduplication**: Detect and merge similar findings across sources
- [ ] **Fact-Checking**: Use LLM to validate claims in findings
- [ ] **Trend Detection**: Identify emerging topics from research over time
- [ ] **Competitor Diff**: Alert when competitor website changes
- [ ] **Scheduled Cycles**: UI to configure research schedules per user
- [ ] **Custom Extractors**: Plugins for specific competitors/sources

## Files Created

```
app/crawler/
├── __init__.py                    # Module exports
├── engine.py                      # CrawlEngine (HTTP, HTML parsing)
├── research.py                    # ResearchEngine (orchestrator)
├── sources.py                     # Curated sources & query generators
├── test_crawler.py                # Unit tests
└── README.md                      # Full documentation

app/api/
└── crawler_routes.py              # REST API endpoints

Root/
└── CRAWLER_INTEGRATION.md         # This file
```

## Questions?

Refer to:
1. `app/crawler/README.md` — Full module documentation
2. `app/crawler/test_crawler.py` — Usage examples in tests
3. `app/api/crawler_routes.py` — API endpoint details
4. `app/crawler/sources.py` — How to add custom sources

The entire module is well-documented with docstrings and examples.
