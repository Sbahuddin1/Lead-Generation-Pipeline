"""
Email Generator — Stage 6
Uses LLM to generate personalized cold outreach emails
positioning Rextag's energy infrastructure data products.
"""

import os
import sys
from typing import List, Dict

# ── Import from parent dir ───────────────────────────────────
PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PARENT)
from my_llm import get_llm_settings


SYSTEM_PROMPT = """You are a sales development representative at Rextag, a company that provides comprehensive energy infrastructure data solutions. Rextag offers:

- GIS data and mapping for pipelines, refineries, power plants, substations, transmission lines, and more
- Asset databases covering upstream, midstream, downstream, power & renewables across North America
- Data deliverables via File Geodatabases, WMS/WFS/REST web services, and The Energy DataLink app
- 19+ years in operation, serving 95% of major U.S. energy companies
- Millions of data records with detailed attributes (owners, operators, statuses, capacities, locations)

Write concise, professional, highly personalized cold outreach emails. The email must:
- Reference specific details from the news/context provided
- Position Rextag's energy infrastructure data as THE solution for their specific project/need
- Be warm but professional — not pushy
- Include a specific call-to-action (e.g., a 15-min demo, data sample request)
- Keep it under 180 words
- Have a subject line that references their specific project/company

Return format:
Subject: [subject line]

[email body]

Best regards,
[Sales Rep Name]
Rextag Corporation"""


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
        max_tokens=500,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def generate_emails(leads: List[Dict]) -> List[Dict]:
    """
    Generate personalized outreach emails for each lead.
    
    Args:
        leads: Enriched leads with person_name, company_name, context, email.
    
    Returns:
        Same leads with added `generated_email` field.
    """
    results = []

    for lead in leads:
        person_name = lead.get("person_name", "").strip()
        person_title = lead.get("person_title", "").strip()
        company_name = lead.get("company_name", "").strip()
        context = lead.get("context", "").strip()
        source_title = lead.get("source_title", "").strip()

        if not company_name:
            lead_copy = lead.copy()
            lead_copy["generated_email"] = "(No company identified)"
            results.append(lead_copy)
            continue

        # Only generate email if we actually found a contact email
        email_addr = lead.get("email", "").strip()
        if not email_addr:
            lead_copy = lead.copy()
            lead_copy["generated_email"] = "(No email found — skipped generation)"
            results.append(lead_copy)
            print(f"[EMAIL-GEN] ⏭ Skipping {company_name} — no email address found")
            continue

        addressee = person_name or f"the team at {company_name}"
        title_str = f", {person_title}" if person_title else ""

        user_prompt = (
            f"Write a cold outreach email to {addressee}{title_str} at {company_name}.\n\n"
            f"Context from recent news:\n"
            f"Article: {source_title}\n"
            f"Relevance: {context}\n\n"
            f"The email should specifically connect Rextag's energy infrastructure data "
            f"to their current project or activity described above."
        )

        try:
            email_text = _call_llm([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
            print(f"[EMAIL-GEN] ✓ Generated email for {addressee} @ {company_name}")
        except Exception as exc:
            print(f"[EMAIL-GEN] Error for {company_name}: {exc}")
            email_text = f"(Email generation failed: {exc})"

        lead_copy = lead.copy()
        lead_copy["generated_email"] = email_text
        results.append(lead_copy)

    print(f"[EMAIL-GEN] Generated {len(results)} emails")
    return results


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    test_leads = [
        {
            "person_name": "John Smith",
            "person_title": "VP of Engineering",
            "company_name": "NextDecade",
            "company_domain": "next-decade.com",
            "context": "NextDecade is building a 27 mtpa LNG export facility in Brownsville, Texas. They need infrastructure data for pipeline routing and facility planning.",
            "source_url": "https://example.com",
            "source_title": "NextDecade Starts Construction on Rio Grande LNG",
            "email": "john.smith@next-decade.com",
            "email_confidence": 85,
        }
    ]

    results = generate_emails(test_leads)
    for r in results:
        print(f"\n{'='*60}")
        print(r["generated_email"])
