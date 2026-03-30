"""
Keyword Filter — Stage 2
Fast regex-based pre-filter to keep only articles
mentioning energy infrastructure topics relevant to Rextag.
"""

import re
from typing import List, Dict

# ── Keyword groups ──────────────────────────────────────────
# Matches articles about companies that might need
# energy infrastructure GIS data / mapping / asset databases.

INFRASTRUCTURE_KEYWORDS = [
    "pipeline", "refinery", "lng", "terminal", "compressor station",
    "power plant", "substation", "transmission line", "solar farm",
    "wind farm", "offshore platform", "drilling", "wellhead",
    "gas processing", "petrochemical", "tank farm", "storage facility",
    "hydrogen plant", "battery storage", "power grid", "distribution network",
    "midstream", "downstream", "upstream", "gathering system",
]

ACTIVITY_KEYWORDS = [
    "acquisition", "expansion", "construction", "new project",
    "permitting", "regulatory filing", "capacity increase", "commissioning",
    "joint venture", "merger", "partnership", "investment",
    "contract awarded", "fid", "final investment decision",
    "groundbreaking", "inaugurated", "completed construction",
    "phase 2", "greenfield", "brownfield", "decommissioning",
]

DATA_NEED_KEYWORDS = [
    "mapping", "gis", "asset management", "infrastructure data",
    "energy data", "route planning", "site selection", "right-of-way",
    "land survey", "geospatial", "data analytics", "digital twin",
]

ALL_KEYWORDS = INFRASTRUCTURE_KEYWORDS + ACTIVITY_KEYWORDS + DATA_NEED_KEYWORDS


def _build_pattern(keywords: List[str]) -> re.Pattern:
    """Build a compiled regex OR-pattern from keyword list."""
    escaped = [re.escape(kw) for kw in keywords]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


# Pre-compile for speed
_PATTERN = _build_pattern(ALL_KEYWORDS)


def filter_articles(
    articles: List[Dict],
    min_matches: int = 1,
) -> List[Dict]:
    """
    Filter articles by keyword relevance.
    
    Args:
        articles: List of {title, link, summary, source, published} dicts.
        min_matches: Minimum keyword matches (in title+summary) to keep article.
    
    Returns:
        Filtered list with an added `matched_keywords` field.
    """
    filtered = []

    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        matches = _PATTERN.findall(text)
        unique_matches = list(set(m.lower() for m in matches))

        if len(unique_matches) >= min_matches:
            article_copy = article.copy()
            article_copy["matched_keywords"] = unique_matches
            filtered.append(article_copy)

    print(f"[KEYWORD] {len(filtered)}/{len(articles)} articles passed keyword filter")
    return filtered


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    # Quick test with sample articles
    test_articles = [
        {
            "title": "Shell Expands LNG Terminal Construction in Texas",
            "summary": "Shell announced a major expansion of its LNG terminal facility in Freeport, Texas...",
            "link": "https://example.com/1",
            "source": "test",
            "published": "",
        },
        {
            "title": "Stock Market Hits Record High",
            "summary": "The S&P 500 closed at a record high today...",
            "link": "https://example.com/2",
            "source": "test",
            "published": "",
        },
        {
            "title": "New Pipeline Project Gets Regulatory Approval",
            "summary": "The permitting process for a new natural gas gathering system...",
            "link": "https://example.com/3",
            "source": "test",
            "published": "",
        },
    ]

    results = filter_articles(test_articles)
    for r in results:
        print(f"\n✓ {r['title']}")
        print(f"  Keywords: {r['matched_keywords']}")
