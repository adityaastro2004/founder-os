"""
Founder OS — Research Sources
===============================
Curated sources for different industries and topics.
RSS feeds, websites, and platforms for monitoring.
"""

from __future__ import annotations


# ============================================================================
# Tech & Startup News
# ============================================================================

TECH_NEWS_SOURCES = [
    {"name": "TechCrunch", "rss": "https://techcrunch.com/feed/", "type": "news"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/", "type": "community"},
    {"name": "Product Hunt", "rss": "https://www.producthunt.com/feed", "type": "launches"},
    {"name": "The Verge", "rss": "https://www.theverge.com/rss/index.xml", "type": "news"},
    {
        "name": "MIT Technology Review",
        "rss": "https://www.technologyreview.com/feed.rss",
        "type": "news",
    },
]

STARTUP_SOURCES = [
    {
        "name": "IndieHackers",
        "url": "https://www.indiehackers.com/",
        "type": "community",
    },
    {"name": "SaaStr", "rss": "https://www.saastr.com/feed/", "type": "saas"},
    {
        "name": "First Round Review",
        "rss": "https://firstround.com/feed.xml",
        "type": "insights",
    },
    {
        "name": "Y Combinator Blog",
        "rss": "https://www.ycombinator.com/feed.rss",
        "type": "insights",
    },
]

# ============================================================================
# Marketing & Growth
# ============================================================================

MARKETING_SOURCES = [
    {
        "name": "Andrew Chen",
        "rss": "https://andrewchen.substack.com/api/v1/posts",
        "type": "insights",
    },
    {
        "name": "Stratechery",
        "rss": "https://stratechery.com/feed/",
        "type": "insights",
    },
    {
        "name": "Marketing Brew",
        "rss": "https://www.marketingbrew.com/feed",
        "type": "news",
    },
]

# ============================================================================
# Customer Signal Platforms
# ============================================================================

CUSTOMER_PLATFORMS = {
    "reddit": "site:reddit.com",
    "producthunt": "site:producthunt.com",
    "g2": "site:g2.com",
    "capterra": "site:capterra.com",
    "trustpilot": "site:trustpilot.com",
    "twitter": "site:twitter.com",
    "twitter_x": "site:x.com",
}

# ============================================================================
# Industry-Specific Sources
# ============================================================================

INDUSTRY_SOURCES = {
    "saas": [
        {"name": "SaaStr", "rss": "https://www.saastr.com/feed/", "type": "saas"},
        {"name": "Stripe Blog", "rss": "https://stripe.com/blog/feed.rss", "type": "insights"},
        {
            "name": "Intercom",
            "rss": "https://www.intercom.com/blog/feed/",
            "type": "insights",
        },
    ],
    "ecommerce": [
        {
            "name": "Shopify Plus",
            "rss": "https://www.shopify.com/blog/plus/feed.xml",
            "type": "insights",
        },
        {
            "name": "Practical Ecommerce",
            "rss": "https://www.practicalecommerce.com/feed/",
            "type": "news",
        },
    ],
    "fintech": [
        {
            "name": "Fintech Magazine",
            "rss": "https://www.fintechmagazine.com/feed",
            "type": "news",
        },
        {
            "name": "PaymentsSource",
            "rss": "https://paymentssource.com/feed/",
            "type": "news",
        },
    ],
    "ai": [
        {
            "name": "AI Business",
            "rss": "https://aibusiness.com/feed/",
            "type": "news",
        },
        {
            "name": "Papers with Code",
            "rss": "https://paperswithcode.com/latest/feed",
            "type": "research",
        },
    ],
    "healthcare": [
        {
            "name": "MobiHealthNews",
            "rss": "https://www.mobihealthnews.com/feed/",
            "type": "news",
        },
        {
            "name": "Healthcare IT News",
            "rss": "https://www.healthcareitnews.com/feed.xml",
            "type": "news",
        },
    ],
}


# ============================================================================
# Helper functions
# ============================================================================

def get_sources_for_industry(industry: str) -> list[dict]:
    """Return relevant RSS/website sources for a given industry."""
    industry_lower = industry.lower().strip()

    # Start with general startup sources
    sources = STARTUP_SOURCES + TECH_NEWS_SOURCES

    # Add industry-specific
    if industry_lower in INDUSTRY_SOURCES:
        sources.extend(INDUSTRY_SOURCES[industry_lower])

    # Add marketing
    sources.extend(MARKETING_SOURCES)

    return sources


def get_customer_signal_queries(
    company_name: str, industry: str, target_audience: str
) -> list[str]:
    """Generate search queries for finding customer signals and sentiment."""
    queries = []

    # Direct product reviews
    queries.append(f"{company_name} reviews")
    queries.append(f"{company_name} reddit")

    # Industry sentiment
    queries.append(f"{industry} problems solutions")
    queries.append(f"{industry} complaints issues")

    # Audience pain points
    if target_audience:
        queries.append(f"{target_audience} {industry} challenges")
        queries.append(f"{target_audience} needs requirements")

    # Competitive comparisons
    queries.append(f"best {industry} tools 2024")
    queries.append(f"{industry} alternatives comparison")

    return queries


def get_competitor_search_queries(
    competitors: list[str], industry: str
) -> list[str]:
    """Generate search queries to monitor competitors."""
    queries = []

    for competitor in competitors:
        queries.append(f"{competitor} news")
        queries.append(f"{competitor} funding announcement")
        queries.append(f"{competitor} product launch")
        queries.append(f"{competitor} pricing 2024")
        queries.append(f"{competitor} reviews complaints")

    # General competitive landscape
    queries.append(f"{industry} market leaders 2024")
    queries.append(f"{industry} startups emerging")
    queries.append(f"{industry} consolidation acquisitions")

    return queries


def get_trend_search_queries(
    industry: str, technologies: list[str], keywords: list[str]
) -> list[str]:
    """Generate search queries for industry trends."""
    queries = []

    # Industry trends
    queries.append(f"{industry} trends 2024")
    queries.append(f"{industry} predictions future")
    queries.append(f"{industry} emerging technologies")

    # Technology trends
    for tech in technologies:
        queries.append(f"{tech} adoption {industry}")
        queries.append(f"{tech} news updates")
        queries.append(f"{tech} best practices 2024")

    # Keyword trends
    for kw in keywords:
        queries.append(f"{kw} trend analysis")

    # Macro trends
    queries.append(f"AI impact {industry}")
    queries.append(f"automation {industry}")

    return queries
