"""
Pipeline Orchestrator
Runs all 6 stages of the lead generation pipeline sequentially,
reporting progress via a callback function.
"""

import asyncio
import time
from typing import Callable, Optional, List, Dict

from feed_aggregator import fetch_all_feeds
from keyword_filter import filter_articles
from llm_filter import filter_with_llm
from contact_extractor import extract_contacts
from email_finder import find_emails
from email_generator import generate_emails


# ── Stage definitions ────────────────────────────────────────
STAGES = [
    {"id": "rss",      "label": "Fetching RSS Feeds",         "pct_start":  0, "pct_end": 15},
    {"id": "keyword",  "label": "Keyword Filtering",          "pct_start": 15, "pct_end": 25},
    {"id": "llm",      "label": "LLM Filtering",              "pct_start": 25, "pct_end": 45},
    {"id": "crawl",    "label": "Crawling & Extracting",      "pct_start": 45, "pct_end": 70},
    {"id": "email",    "label": "Finding Email Addresses",    "pct_start": 70, "pct_end": 82},
    {"id": "generate", "label": "Generating Outreach Emails", "pct_start": 82, "pct_end": 98},
    {"id": "done",     "label": "Complete",                   "pct_start": 100, "pct_end": 100},
]


def run_pipeline(
    on_progress: Optional[Callable] = None,
    max_articles_per_feed: int = 5,
    max_email_lookups: int = 2,
) -> Dict:
    """
    Execute the full 6-stage lead generation pipeline.
    
    Args:
        on_progress: Callback(stage_id, pct, label, stats) for progress updates.
        max_articles_per_feed: Max articles to pull from each RSS feed.
    
    Returns:
        Dict with keys: leads (list), stats (dict).
    """
    stats = {
        "articles_scanned": 0,
        "keyword_matches": 0,
        "llm_approved": 0,
        "contacts_extracted": 0,
        "emails_found": 0,
        "emails_generated": 0,
        "duration_seconds": 0,
    }
    
    def progress(stage_id: str, pct: int, label: str):
        if on_progress:
            on_progress(stage_id, pct, label, stats)

    start_time = time.time()

    # ── Stage 1: Fetch RSS feeds ─────────────────────────────
    progress("rss", 5, "Fetching articles from 6 RSS sources...")
    articles = fetch_all_feeds(max_per_feed=max_articles_per_feed)
    stats["articles_scanned"] = len(articles)
    progress("rss", 15, f"Fetched {len(articles)} articles")

    if not articles:
        stats["duration_seconds"] = round(time.time() - start_time, 1)
        progress("done", 100, "No articles found from RSS feeds")
        return {"leads": [], "stats": stats}

    # ── Stage 2: Keyword filter ──────────────────────────────
    progress("keyword", 18, f"Filtering {len(articles)} articles by keywords...")
    keyword_matched = filter_articles(articles)
    stats["keyword_matches"] = len(keyword_matched)
    progress("keyword", 25, f"{len(keyword_matched)} articles matched keywords")

    if not keyword_matched:
        stats["duration_seconds"] = round(time.time() - start_time, 1)
        progress("done", 100, "No articles matched keywords")
        return {"leads": [], "stats": stats}

    # ── Stage 3: LLM filter ──────────────────────────────────
    progress("llm", 30, f"AI analyzing {len(keyword_matched)} articles...")
    llm_approved = filter_with_llm(keyword_matched)
    stats["llm_approved"] = len(llm_approved)
    progress("llm", 45, f"{len(llm_approved)} articles approved by AI")

    if not llm_approved:
        stats["duration_seconds"] = round(time.time() - start_time, 1)
        progress("done", 100, "No lead-worthy articles found")
        return {"leads": [], "stats": stats}

    # ── Stage 4: Crawl & extract contacts ────────────────────
    progress("crawl", 50, f"Crawling {len(llm_approved)} article pages...")
    leads = asyncio.run(extract_contacts(llm_approved))
    stats["contacts_extracted"] = len(leads)
    progress("crawl", 70, f"Extracted {len(leads)} contacts")

    if not leads:
        stats["duration_seconds"] = round(time.time() - start_time, 1)
        progress("done", 100, "No contacts found in articles")
        return {"leads": [], "stats": stats}

    # Drop leads without a person name or company domain — can't look up emails
    viable_leads = [l for l in leads if l.get("person_name") and l.get("company_domain")]
    skipped = len(leads) - len(viable_leads)
    if skipped:
        print(f"[PIPELINE] Dropped {skipped} leads without name/domain")
    stats["contacts_extracted"] = len(viable_leads)
    progress("crawl", 70, f"Extracted {len(viable_leads)} viable contacts")

    if not viable_leads:
        stats["duration_seconds"] = round(time.time() - start_time, 1)
        progress("done", 100, "No contacts with names + domains found")
        return {"leads": [], "stats": stats}

    # ── Stage 5: Find emails (only for viable leads) ─────────
    progress("email", 75, f"Looking up emails for {len(viable_leads)} leads...")
    leads = find_emails(viable_leads, max_lookups=max_email_lookups)
    stats["emails_found"] = sum(1 for l in leads if l.get("email"))
    progress("email", 82, f"Found {stats['emails_found']} email addresses")

    # ── Stage 6: Generate outreach emails (only for leads WITH emails) ──
    leads_with_email = [l for l in leads if l.get("email")]
    leads_without_email = [l for l in leads if not l.get("email")]

    if leads_with_email:
        progress("generate", 85, f"AI writing {len(leads_with_email)} emails (skipping {len(leads_without_email)} without email)...")
        leads_with_email = generate_emails(leads_with_email)
    else:
        progress("generate", 98, "No leads with emails — skipping email generation")

    # Mark skipped leads
    for l in leads_without_email:
        l["generated_email"] = "(No email found — skipped generation)"

    all_leads = leads_with_email + leads_without_email
    stats["emails_generated"] = sum(1 for l in all_leads if l.get("generated_email") and not l["generated_email"].startswith("("))
    progress("generate", 98, f"Generated {stats['emails_generated']} emails")

    # ── Done ─────────────────────────────────────────────────
    stats["duration_seconds"] = round(time.time() - start_time, 1)
    progress("done", 100, f"Pipeline complete! {len(all_leads)} leads processed in {stats['duration_seconds']}s")

    return {"leads": all_leads, "stats": stats}


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    def on_progress(stage_id, pct, label, stats):
        print(f"[{pct:3d}%] [{stage_id:>8s}] {label}")

    print("=" * 60)
    print("  REXTAG LEAD GEN — PIPELINE TEST")
    print("=" * 60)

    result = run_pipeline(on_progress=on_progress)

    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(result['leads'])} leads")
    print(f"  STATS: {result['stats']}")
    print(f"{'='*60}")

    for i, lead in enumerate(result["leads"]):
        print(f"\n--- Lead {i+1} ---")
        print(f"  Person:  {lead.get('person_name', 'N/A')}")
        print(f"  Company: {lead.get('company_name', 'N/A')}")
        print(f"  Email:   {lead.get('email', 'N/A')}")
        print(f"  Source:  {lead.get('source_url', 'N/A')}")
        print(f"  Email preview: {lead.get('generated_email', '')[:100]}...")
