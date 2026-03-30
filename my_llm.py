import os
from typing import Dict, Optional

from dotenv import load_dotenv


def get_llm_settings() -> Dict[str, Optional[str]]:
    """Return minimal LLMConfig settings for API extraction."""
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment.")

    return {
        "provider": "gpt-4o-mini",
        "api_token": api_key.strip() if api_key else "",
        "base_url": None,
    }