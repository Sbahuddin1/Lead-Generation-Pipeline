"""
RSS Feed Aggregator — Stage 1
Fetches articles from multiple energy-focused RSS feeds,
deduplicates by URL, and returns a unified article list.
"""

import feedparser
from datetime import datetime
from typing import List, Dict, Optional

# ── Energy-focused RSS sources ──────────────────────────────
RSS_FEEDS = [
    {
        "name": "Rigzone",
        "url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx",
    },
    {
        "name": "Google News (Energy)",
        "url": (
            "https://news.google.com/rss/search?"
            "q=energy+infrastructure+oil+gas+pipeline+renewable&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "GlobeNewsWire Energy",
        "url": "https://www.globenewswire.com/RssFeed/subjectcode/25-Energy/feedTitle/GlobeNewswire+-+Energy",
    },
    {
        "name": "OilPrice.com",
        "url": "https://oilprice.com/rss/main",
    },
    {
        "name": "EIA Today in Energy",
        "url": "https://www.eia.gov/rss/todayinenergy.xml",
    },
    {
        "name": "Google News (Pipeline Construction)",
        "url": (
            "https://news.google.com/rss/search?"
            "q=pipeline+construction+LNG+terminal+refinery+expansion&hl=en-US&gl=US&ceid=US:en"
        ),
    },
]

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"


def _parse_feed(feed_config: dict) -> List[Dict]:
    """Parse a single RSS feed and return normalized articles."""
    name = feed_config["name"]
    url = feed_config["url"]

    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
    except Exception as exc:
        print(f"[FEED] Error fetching '{name}': {exc}")
        return []

    articles = []
    for entry in feed.entries:
        link = entry.get("link", "").strip()
        if not link:
            continue

        # Parse published date
        published = ""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6]).isoformat()
            except Exception:
                published = entry.get("published", "")

        title = entry.get("title", "").strip()
        summary = entry.get("summary", entry.get("description", "")).strip()
        # Strip HTML tags from summary
        import re
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        articles.append({
            "title": title,
            "link": link,
            "summary": summary[:1000],  # cap length
            "source": name,
            "published": published,
        })

    print(f"[FEED] {name}: fetched {len(articles)} articles")
    return articles


def fetch_all_feeds(
    feeds: Optional[List[Dict]] = None,
    max_per_feed: int = 5,
) -> List[Dict]:
    """
    Fetch all RSS feeds, deduplicate by URL, return unified list.
    
    Args:
        feeds: list of {"name", "url"} dicts. Defaults to RSS_FEEDS.
        max_per_feed: max articles to take from each feed.
    
    Returns:
        List of {title, link, summary, source, published} dicts.
    """
    feeds = feeds or RSS_FEEDS
    all_articles = []
    seen_urls = set()

    for feed_cfg in feeds:
        articles = _parse_feed(feed_cfg)
        for art in articles[:max_per_feed]:
            url = art["link"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(art)

    print(f"[FEED] Total unique articles: {len(all_articles)}")
    return all_articles


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    articles = fetch_all_feeds()
    for i, a in enumerate(articles[:10]):
        print(f"\n{i+1}. [{a['source']}] {a['title']}")
        print(f"   {a['link']}")
        print(f"   {a['summary'][:120]}...")
