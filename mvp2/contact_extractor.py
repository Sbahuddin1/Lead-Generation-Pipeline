"""
Contact Extractor — Stage 4
Crawls LLM-approved article pages and uses GPT to extract
person names, company names, domains, and context.
"""

import asyncio
import json
import os
import sys
from typing import List, Dict, Optional

# ── Import from parent dir ───────────────────────────────────
PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PARENT)

from my_llm import get_llm_settings
from crawler import scrape_pages_fully


EXTRACTION_PROMPT = """You are a data extraction specialist. Given a news article about energy/infrastructure, extract ALL people and companies mentioned.

For each person mentioned, create an entry with:
- person_name: Full name
- person_title: Their job title if mentioned, otherwise ""
- company_name: The company they work for
- company_domain: Best guess at the company's website domain (e.g., "nextera.com", "shell.com")

Also provide:
- context: A 2-3 sentence summary of WHY this company might need energy infrastructure GIS data, mapping, or asset databases from Rextag. Focus on the specific project, expansion, or activity mentioned.

Return a JSON object with this structure:
{
    "contacts": [
        {
            "person_name": "John Smith",
            "person_title": "VP of Engineering",
            "company_name": "NextEra Energy",
            "company_domain": "nextera.com"
        }
    ],
    "company_name": "primary company in article",
    "company_domain": "primary company domain",
    "context": "2-3 sentence context about why they need Rextag"
}

If no specific people are named, return an empty contacts array but still fill in company_name, company_domain, and context.

IMPORTANT: Only extract REAL information from the article. Do not make up names or details."""


def _call_llm(messages: List[Dict]) -> str:
    """Call LLM and return response text."""
    import litellm
    settings = get_llm_settings()
    litellm.drop_params = True
    response = litellm.completion(
        model=settings["provider"],
        api_key=settings["api_token"],
        api_base=settings.get("base_url"),
        messages=messages,
        max_tokens=1500,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _extract_from_text(article: Dict, page_text: str) -> Dict:
    """Use LLM to extract contacts from crawled page text."""
    # Cap context to avoid token overflow
    truncated = page_text[:8000]

    user_prompt = (
        f"Article Title: {article.get('title', '')}\n"
        f"Source: {article.get('source', '')}\n"
        f"Company hint from previous analysis: {article.get('llm_company', '')}\n\n"
        f"Full article text:\n{truncated}\n\n"
        "Extract all contacts and context as described."
    )

    try:
        raw = _call_llm([
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        # Handle markdown code blocks
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw.strip())
        return data
    except Exception as exc:
        print(f"[EXTRACT] Error extracting from '{article.get('title', '')[:50]}': {exc}")
        return {
            "contacts": [],
            "company_name": article.get("llm_company", ""),
            "company_domain": "",
            "context": article.get("llm_reason", ""),
        }


async def extract_contacts(
    articles: List[Dict],
    max_concurrent: int = 4,
) -> List[Dict]:
    """
    Crawl article pages and extract contacts via LLM.
    
    Args:
        articles: LLM-approved articles with links.
        max_concurrent: Max concurrent page crawls.
    
    Returns:
        List of lead dicts: {person_name, person_title, company_name,
        company_domain, context, source_url, source_title}
    """
    if not articles:
        return []

    # Step 1: Crawl all article pages
    urls = [a["link"] for a in articles]
    print(f"[EXTRACT] Crawling {len(urls)} article pages...")

    try:
        pages = await scrape_pages_fully(
            urls=urls,
            max_concurrent=max_concurrent,
            use_undetected=True,
            headless=True,
        )
    except Exception as exc:
        print(f"[EXTRACT] Crawler error: {exc}")
        pages = []

    # Build URL → markdown lookup
    url_to_text = {p["url"]: p["markdown"] for p in pages if p.get("markdown")}
    print(f"[EXTRACT] Successfully crawled {len(url_to_text)}/{len(urls)} pages")

    # Step 2: Extract contacts from each page
    leads = []
    for article in articles:
        page_text = url_to_text.get(article["link"], "")

        if not page_text:
            # Skip articles we couldn't crawl — no point wasting LLM tokens
            print(f"[EXTRACT] ⏭ Skipping (no content): {article.get('title', '')[:60]}")
            continue

        extraction = _extract_from_text(article, page_text)

        # Build lead entries
        company = extraction.get("company_name", article.get("llm_company", ""))
        domain = extraction.get("company_domain", "")
        context = extraction.get("context", article.get("llm_reason", ""))

        contacts = extraction.get("contacts", [])
        if contacts:
            for contact in contacts:
                leads.append({
                    "person_name": contact.get("person_name", ""),
                    "person_title": contact.get("person_title", ""),
                    "company_name": contact.get("company_name", company),
                    "company_domain": contact.get("company_domain", domain),
                    "context": context,
                    "source_url": article["link"],
                    "source_title": article["title"],
                })
        else:
            # No specific people found, still record the company lead
            leads.append({
                "person_name": "",
                "person_title": "",
                "company_name": company,
                "company_domain": domain,
                "context": context,
                "source_url": article["link"],
                "source_title": article["title"],
            })

    print(f"[EXTRACT] Extracted {len(leads)} leads from {len(articles)} articles")
    return leads


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    test_articles = [
        {
            "title": "NextDecade Starts Construction on Rio Grande LNG",
            "summary": "NextDecade Corporation announced construction on its LNG facility in Brownsville, Texas.",
            "link": "https://www.rigzone.com/news/nextdecade_starts_construction-30-mar-2026",
            "source": "Rigzone",
            "published": "",
            "matched_keywords": ["lng", "construction"],
            "llm_company": "NextDecade",
            "llm_reason": "Building new LNG export facility",
        }
    ]

    results = asyncio.run(extract_contacts(test_articles))
    for r in results:
        print(f"\n  Person: {r['person_name']}")
        print(f"  Company: {r['company_name']} ({r['company_domain']})")
        print(f"  Context: {r['context']}")
