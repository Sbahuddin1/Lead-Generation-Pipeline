"""
Rextag Lead Gen AI — MVP1 Backend
Flask server that:
  1. Serves the frontend
  2. Searches Google News for each company (top 2 article URLs)
  3. Crawls all 6 URLs using the existing crawler
  4. Asks LLM to write a personalized outreach email per lead
  5. Returns results as JSON to the frontend
"""

import asyncio
import os
import sys
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import feedparser
import requests

# ── allow importing from the parent directory (crawler.py, my_llm.py)
PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PARENT)

from my_llm import get_llm_settings
from crawler import scrape_pages_fully

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# ─────────────────────────────────────────────
#  HARDCODED LEADS  (person, company, title)
# ─────────────────────────────────────────────
DEFAULT_LEADS = [
    {"person": "John Mitchell",   "company": "Shell",       "title": "VP of Engineering"},
    {"person": "Sarah Chen",      "company": "ExxonMobil",  "title": "Director of Operations"},
    {"person": "Ahmed Al-Rashid", "company": "BP",          "title": "Head of Clean Energy"},
]

# ─────────────────────────────────────────────
#  HELPER: Google News RSS → top N article URLs
# ─────────────────────────────────────────────
def get_news_urls(company_name: str, n: int = 2) -> list[str]:
    """
    Fetch top-N news article URLs for `company_name` via the
    Google News RSS feed (no API key needed).
    Uses feedparser so item <link> tags are properly extracted.
    """
    query = requests.utils.quote(company_name + " news")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(
            rss_url,
            request_headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        urls = []
        for entry in feed.entries[:n]:
            link = entry.get("link", "").strip()
            if link:
                urls.append(link)
        print(f"[NEWS] {company_name}: found {len(urls)} articles")
        return urls
    except Exception as exc:
        print(f"[NEWS] Failed for '{company_name}': {exc}")
        return []


# ─────────────────────────────────────────────
#  HELPER: call LiteLLM / OpenRouter
# ─────────────────────────────────────────────
def generate_email(lead: dict, article_texts: list[str]) -> str:
    """
    Ask the LLM to write a personalized outreach email based on scraped articles.
    """
    import litellm

    settings = get_llm_settings()
    combined_news = "\n\n---\n\n".join(article_texts[:2])[:6000]   # cap context

    system_prompt = (
        "You are Slah, a solutions consultant at EdgeC, a company that provides "
        "specialized engineering, digital transformation, and AI-driven consulting "
        "services for the oil & gas, clean energy, and industrial sectors. "
        "Write concise, professional, and highly personalized cold outreach emails. "
        "The email must reference specific details from the news provided, position "
        "EdgeC as the right partner for the challenges/opportunities mentioned, and "
        "include a clear call to action. Keep it under 200 words."
    )

    user_prompt = (
        f"Write a cold outreach email to {lead['person']}, {lead['title']} at "
        f"{lead['company']}.\n\n"
        f"Here is recent news about {lead['company']}:\n\n{combined_news}\n\n"
        "The email should:\n"
        "- Open by referencing the specific news/topic above\n"
        "- Explain how EdgeC can help with that challenge or opportunity\n"
        "- Be signed by Slah at EdgeC\n"
        "- Have a short subject line suggestion at the top prefixed with 'Subject: '"
    )

    litellm.drop_params = True
    response = litellm.completion(
        model=settings["provider"],
        api_key=settings["api_token"],
        api_base=settings.get("base_url"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=400,
        temperature=0.7,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(
            f"LLM returned empty content. finish_reason={response.choices[0].finish_reason!r}"
        )
    return content.strip()


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "index.html")


@app.route("/start", methods=["POST"])
def start():
    """
    Main pipeline endpoint.
    Accepts optional JSON body with `leads` list; otherwise uses DEFAULT_LEADS.
    Returns a list of result objects.
    """
    data = request.get_json(silent=True) or {}
    leads = data.get("leads", DEFAULT_LEADS)

    results = []

    # ── Step 1: gather news URLs for each company
    all_urls: list[str] = []
    lead_url_map: list[dict] = []   # {lead, urls: []}

    for lead in leads:
        urls = get_news_urls(lead["company"], n=2)
        lead_url_map.append({"lead": lead, "urls": urls})
        all_urls.extend(urls)
        print(f"[NEWS] {lead['company']}: {urls}")

    # ── Step 2: crawl all URLs in one parallel batch
    if all_urls:
        pages_list = asyncio.run(
            scrape_pages_fully(all_urls, max_concurrent=6, use_undetected=True, headless=True)
        )
        # Build lookups: by original URL and by resolved (final) URL.
        # crawl4ai follows redirects so the stored URL may differ from the feed URL.
        url_to_text = {p["url"]: p["markdown"] for p in pages_list}
        # Ordered list of all successfully scraped texts (positional fallback)
        ordered_texts = [p["markdown"] for p in pages_list if p.get("markdown")]
    else:
        url_to_text = {}
        ordered_texts = []

    # ── Step 3: generate an email per lead
    texts_cursor = 0   # walk through ordered_texts when direct lookup misses
    for item in lead_url_map:
        lead = item["lead"]
        urls = item["urls"]

        # Try direct URL match first; fall back to positional crawl results
        article_texts = []
        for u in urls:
            text = url_to_text.get(u, "")
            if text:
                article_texts.append(text)
                texts_cursor += 1
            elif texts_cursor < len(ordered_texts):
                article_texts.append(ordered_texts[texts_cursor])
                texts_cursor += 1
        if not article_texts and texts_cursor < len(ordered_texts):
            article_texts = ordered_texts[texts_cursor:texts_cursor + 2]
            texts_cursor += len(article_texts)

        if article_texts:
            try:
                email_text = generate_email(lead, article_texts)
            except Exception as exc:
                print(f"[LLM] Error for {lead['company']}: {exc}")
                email_text = f"(Email generation failed: {exc})"
        else:
            email_text = "(No articles found — could not generate email)"

        results.append({
            "person":   lead["person"],
            "company":  lead["company"],
            "title":    lead["title"],
            "urls":     urls,
            "email":    email_text,
        })

    return jsonify(results)


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
