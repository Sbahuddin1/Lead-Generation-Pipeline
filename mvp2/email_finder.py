"""
Email Finder — Stage 5
Uses Hunter.io API (pyhunter) to find email addresses
for extracted contacts by name + company domain.
Falls back to domain search when individual lookup fails.
"""

import os
from typing import List, Dict, Optional
from dotenv import load_dotenv


MAX_HUNTER_LOOKUPS = 2  # Hard cap — free tier is 25/month, conserve credits
HUNTER_DELAY_SECONDS = 2  # Delay between API calls to avoid rate limiting


def _get_hunter_key() -> Optional[str]:
    """Load Hunter.io API key from environment."""
    load_dotenv()
    key = os.getenv("HUNTER_API_KEY", "").strip()
    return key if key else None


def find_emails(leads: List[Dict], max_lookups: int = MAX_HUNTER_LOOKUPS) -> List[Dict]:
    """
    Enrich leads with email addresses using Hunter.io.
    
    For each lead with a person_name and company_domain:
    1. Try email_finder (name + domain → specific email)
    2. Fallback to domain_search (find any emails at domain)
    
    If HUNTER_API_KEY is not set, uses email pattern guessing as fallback.
    
    Args:
        leads: List of lead dicts from contact_extractor.
    
    Returns:
        Same list with added `email` and `email_confidence` fields.
    """
    hunter_key = _get_hunter_key()

    if hunter_key:
        return _find_with_hunter(leads, hunter_key, max_lookups)
    else:
        print("[EMAIL] No HUNTER_API_KEY found. Using email pattern guessing fallback.")
        return _find_with_pattern(leads)


def _find_with_hunter(leads: List[Dict], api_key: str, max_lookups: int = MAX_HUNTER_LOOKUPS) -> List[Dict]:
    """Use Hunter.io API to find emails."""
    try:
        from pyhunter import PyHunter
        hunter = PyHunter(api_key)
    except ImportError:
        print("[EMAIL] pyhunter not installed. Run: pip install pyhunter")
        return _find_with_pattern(leads)
    except Exception as exc:
        print(f"[EMAIL] Hunter.io init error: {exc}")
        return _find_with_pattern(leads)

    import time as _time

    enriched = []
    api_calls_made = 0

    for lead in leads:
        lead_copy = lead.copy()
        domain = lead.get("company_domain", "").strip()
        person_name = lead.get("person_name", "").strip()

        if not domain:
            lead_copy["email"] = ""
            lead_copy["email_confidence"] = 0
            enriched.append(lead_copy)
            continue

        # Check if we've hit our API call limit
        if api_calls_made >= max_lookups:
            print(f"[EMAIL] ⏸ Skipping {person_name or domain} — reached {max_lookups} lookup limit")
            lead_copy["email"] = ""
            lead_copy["email_confidence"] = 0
            lead_copy["email_note"] = f"Skipped — {max_lookups} lookup limit reached"
            enriched.append(lead_copy)
            continue

        # Try specific person lookup
        if person_name:
            parts = person_name.split()
            first_name = parts[0] if parts else ""
            last_name = parts[-1] if len(parts) > 1 else ""

            try:
                result = hunter.email_finder(
                    domain=domain,
                    first_name=first_name,
                    last_name=last_name,
                )
                api_calls_made += 1
                if result and isinstance(result, dict) and result.get("email"):
                    lead_copy["email"] = result["email"]
                    lead_copy["email_confidence"] = result.get("score", 0)
                    print(f"[EMAIL] ✓ Found: {result['email']} (score: {result.get('score', '?')})")
                    enriched.append(lead_copy)
                    _time.sleep(HUNTER_DELAY_SECONDS)
                    continue
            except Exception as exc:
                api_calls_made += 1
                print(f"[EMAIL] Hunter finder failed for {person_name}@{domain}: {exc}")

        # Fallback: domain search
        try:
            api_calls_made += 1
            _time.sleep(HUNTER_DELAY_SECONDS)
            domain_result = hunter.domain_search(domain)
            if domain_result and isinstance(domain_result, dict):
                emails = domain_result.get("emails", [])
                if emails:
                    best = emails[0]
                    lead_copy["email"] = best.get("value", "")
                    lead_copy["email_confidence"] = best.get("confidence", 0)
                    # Update person name if we found one
                    if not person_name:
                        fn = best.get("first_name", "")
                        ln = best.get("last_name", "")
                        if fn and ln:
                            lead_copy["person_name"] = f"{fn} {ln}"
                    print(f"[EMAIL] ✓ Domain search: {lead_copy['email']}")
                    enriched.append(lead_copy)
                    continue
        except Exception as exc:
            print(f"[EMAIL] Hunter domain search failed for {domain}: {exc}")

        # No results from Hunter
        lead_copy["email"] = ""
        lead_copy["email_confidence"] = 0
        enriched.append(lead_copy)

    found = sum(1 for l in enriched if l.get("email"))
    print(f"[EMAIL] Found emails for {found}/{len(enriched)} leads")
    return enriched


def _find_with_pattern(leads: List[Dict]) -> List[Dict]:
    """
    Fallback: Generate common email patterns when Hunter.io is not available.
    Generates firstname.lastname@domain as the most common pattern.
    """
    enriched = []
    for lead in leads:
        lead_copy = lead.copy()
        domain = lead.get("company_domain", "").strip()
        person_name = lead.get("person_name", "").strip()

        if domain and person_name:
            parts = person_name.lower().split()
            first = parts[0] if parts else ""
            last = parts[-1] if len(parts) > 1 else ""

            if first and last:
                # Generate common patterns
                patterns = [
                    f"{first}.{last}@{domain}",
                    f"{first[0]}{last}@{domain}",
                    f"{first}{last[0]}@{domain}",
                ]
                lead_copy["email"] = patterns[0]  # Most common pattern
                lead_copy["email_confidence"] = 30  # Low confidence (guessed)
                lead_copy["email_alternatives"] = patterns[1:]
                print(f"[EMAIL] ⚡ Pattern guess: {patterns[0]}")
            else:
                lead_copy["email"] = ""
                lead_copy["email_confidence"] = 0
        else:
            lead_copy["email"] = ""
            lead_copy["email_confidence"] = 0

        enriched.append(lead_copy)

    found = sum(1 for l in enriched if l.get("email"))
    print(f"[EMAIL] Generated pattern emails for {found}/{len(enriched)} leads")
    return enriched


# ── Standalone test ──────────────────────────────────────────
if __name__ == "__main__":
    test_leads = [
        {
            "person_name": "John Smith",
            "person_title": "VP Engineering",
            "company_name": "NextDecade",
            "company_domain": "next-decade.com",
            "context": "Building LNG export facility",
            "source_url": "https://example.com",
            "source_title": "Test",
        },
        {
            "person_name": "",
            "person_title": "",
            "company_name": "Unknown Corp",
            "company_domain": "",
            "context": "No domain available",
            "source_url": "https://example.com/2",
            "source_title": "Test 2",
        },
    ]

    results = find_emails(test_leads)
    for r in results:
        print(f"\n  {r['person_name']} @ {r['company_name']}")
        print(f"  Email: {r.get('email', 'N/A')} (confidence: {r.get('email_confidence', 0)})")
