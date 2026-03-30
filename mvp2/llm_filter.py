"""
LLM Filter — Stage 3
Uses GPT to classify keyword-matched articles as lead-worthy or not.
Processes articles in batches to minimize API calls.
"""

import json
import os
import sys
from typing import List, Dict

# ── Import LLM settings from parent dir ──────────────────────
PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PARENT)
from my_llm import get_llm_settings

BATCH_SIZE = 5  # articles per LLM call


SYSTEM_PROMPT = """You are an expert lead qualification analyst for Rextag, a company that sells energy infrastructure GIS data, mapping solutions, and asset databases to energy companies.

Your job is to analyze news articles and determine if they mention a company that might be a potential customer for Rextag's products.

A company is a GOOD LEAD if:
- They are building, expanding, or acquiring energy infrastructure (pipelines, refineries, LNG terminals, power plants, solar/wind farms, substations, etc.)
- They need infrastructure data for planning, routing, permitting, or asset management
- They are making significant capital investments in energy projects
- They are involved in mergers/acquisitions of energy assets

A company is NOT a good lead if:
- The article is about financial results only (stock price, earnings)
- It's about policy/politics without specific company projects
- It's about retail energy prices for consumers
- It's about a company Rextag already likely serves (very large companies like ExxonMobil, Shell, BP, Chevron are still leads — they have many departments)

For each article, respond with a JSON object:
{"verdict": "YES" or "NO", "company": "company name if YES", "reason": "brief 1-sentence reason"}
"""


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


def _classify_batch(articles: List[Dict]) -> List[Dict]:
    """Classify a batch of articles via LLM. Returns list of verdicts."""
    article_texts = []
    for i, art in enumerate(articles):
        article_texts.append(
            f"Article {i+1}:\n"
            f"Title: {art['title']}\n"
            f"Summary: {art['summary'][:500]}\n"
            f"Keywords matched: {', '.join(art.get('matched_keywords', []))}"
        )

    user_prompt = (
        "Classify each article below. Return a JSON array of objects, one per article, "
        "in the same order. Each object must have: verdict, company, reason.\n\n"
        + "\n\n".join(article_texts)
    )

    try:
        raw = _call_llm([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        # Extract JSON from response (handle markdown code blocks)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        verdicts = json.loads(raw.strip())
        if isinstance(verdicts, dict):
            verdicts = [verdicts]
        return verdicts
    except Exception as exc:
        print(f"[LLM-FILTER] Error classifying batch: {exc}")
        # On error, pass all through (fail-open)
        return [{"verdict": "YES", "company": "unknown", "reason": "classification error"} for _ in articles]


def filter_with_llm(
    articles: List[Dict],
    batch_size: int = BATCH_SIZE,
) -> List[Dict]:
    """
    Use LLM to filter articles to only lead-worthy ones.
    
    Args:
        articles: Keyword-filtered article list.
        batch_size: Number of articles per LLM call.
    
    Returns:
        Filtered articles with added `llm_company` and `llm_reason` fields.
    """
    approved = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        verdicts = _classify_batch(batch)

        for j, article in enumerate(batch):
            if j < len(verdicts):
                v = verdicts[j]
                if v.get("verdict", "").upper() == "YES":
                    art_copy = article.copy()
                    art_copy["llm_company"] = v.get("company", "")
                    art_copy["llm_reason"] = v.get("reason", "")
                    approved.append(art_copy)
                    print(f"[LLM-FILTER] ✓ {article['title'][:60]}... → {v.get('company', '?')}")
                else:
                    print(f"[LLM-FILTER] ✗ {article['title'][:60]}... → {v.get('reason', '?')}")
            else:
                # Verdict list shorter than batch — pass through
                approved.append(article.copy())

    print(f"[LLM-FILTER] {len(approved)}/{len(articles)} articles approved by LLM")
    return approved


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    test_articles = [
        {
            "title": "NextDecade Starts Construction on Rio Grande LNG Export Facility",
            "summary": "NextDecade Corporation has announced the start of construction on its Rio Grande LNG export facility in Brownsville, Texas. The project will have a capacity of 27 mtpa.",
            "link": "https://example.com/1",
            "source": "Rigzone",
            "published": "",
            "matched_keywords": ["lng", "construction"],
        },
        {
            "title": "Oil Prices Rise on OPEC Production Cut Extension",
            "summary": "Crude oil prices increased today after OPEC announced an extension of production cuts through the end of the year.",
            "link": "https://example.com/2",
            "source": "OilPrice.com",
            "published": "",
            "matched_keywords": ["upstream"],
        },
    ]

    results = filter_with_llm(test_articles)
    for r in results:
        print(f"\n✓ {r['title']}")
        print(f"  Company: {r.get('llm_company')}")
        print(f"  Reason: {r.get('llm_reason')}")
