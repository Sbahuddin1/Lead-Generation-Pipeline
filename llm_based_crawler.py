import asyncio
import json
from typing import Dict, List

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    LLMConfig,
    LLMExtractionStrategy,
    RateLimiter,
    UndetectedAdapter,
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.async_dispatcher import SemaphoreDispatcher

from my_llm import get_llm_settings

try:
    import litellm

    litellm.suppress_debug_info = True
except Exception:
    pass


def make_llm_config() -> LLMConfig:
    settings = get_llm_settings()
    kwargs = {"provider": settings["provider"], "api_token": settings["api_token"]}
    if settings.get("base_url"):
        kwargs["base_url"] = settings["base_url"]
    return LLMConfig(**kwargs)


def parse_extracted_payload(raw: str) -> Dict[str, str]:
    """Aggregate chunked LLM extraction payloads into one final decision.

    Crawl4AI can return a list of objects when chunking is enabled. A single
    article-level decision should be based on all chunk outputs, not only the
    first one.
    """
    result: Dict[str, str] = {"talks_about_hydrogen": False, "summary": ""}
    if not raw:
        return result

    try:
        payload = json.loads(raw)
    except Exception:
        return result

    if isinstance(payload, dict):
        talks = bool(payload.get("talks_about_hydrogen", False))
        summary = str(payload.get("summary", "")).strip()
        return {"talks_about_hydrogen": talks, "summary": summary}

    if not isinstance(payload, list):
        return result

    summaries: List[str] = []
    talks_about_hydrogen = False

    for item in payload:
        if not isinstance(item, dict):
            continue

        # Keep existing warning behavior when provider truncates output.
        msg = str(item.get("content", ""))
        if "finish_reason: length" in msg:
            result["truncated"] = "true"

        if "talks_about_hydrogen" not in item:
            continue

        if bool(item.get("talks_about_hydrogen", False)):
            talks_about_hydrogen = True

        summary = str(item.get("summary", "")).strip()
        if summary:
            summaries.append(summary)

    if summaries:
        # Keep a short merged summary to avoid long output spam.
        result["summary"] = " ".join(summaries)[:400].strip()

    result["talks_about_hydrogen"] = talks_about_hydrogen
    return result


async def crawl_hydrogen(
    urls: List[str],
    max_concurrent: int = 24,
    use_undetected: bool = False,
) -> List[Dict[str, str]]:
    schema = {
        "type": "object",
        "properties": {
            "talks_about_hydrogen": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["talks_about_hydrogen", "summary"],
    }

    llm_strategy = LLMExtractionStrategy(
        llm_config=make_llm_config(),
        schema=schema,
        extraction_type="schema",
        instruction=(
            "Return JSON only with talks_about_hydrogen (boolean) and summary (max 2 short sentences)."
        ),
        input_format="markdown",
        chunk_token_threshold=3200,
        apply_chunking=True,
        overlap_rate=0.0,
        extra_args={"temperature": 0.0, "max_tokens": 700},
    )

    run_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode=CacheMode.BYPASS,
        stream=False,
        magic=True,
        simulate_user=True,
        remove_overlay_elements=True,
        max_retries=1,
        wait_until="domcontentloaded",
        page_timeout=22000,
        delay_before_return_html=0.0,
    )

    dispatcher = SemaphoreDispatcher(
        max_session_permit=max(1, max_concurrent),
        rate_limiter=RateLimiter(
            base_delay=(0.05, 0.2),
            max_delay=2.5,
            max_retries=1,
            rate_limit_codes=[429, 503],
        ),
    )

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        light_mode=True,
        text_mode=True,
        enable_stealth=True,
        user_agent_mode="random",
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    hits: List[Dict[str, str]] = []

    crawler_kwargs = {"config": browser_config}
    if use_undetected:
        crawler_kwargs["crawler_strategy"] = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            browser_adapter=UndetectedAdapter(),
        )

    async with AsyncWebCrawler(**crawler_kwargs) as crawler:
        results = await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher,
        )

        for result in results:
            if not result.success:
                print(f"FAIL: {result.url} | {str(result.error_message)[:120]}")
                continue

            data = parse_extracted_payload(result.extracted_content or "")

            if data.get("truncated") == "true":
                print(f"WARN: {result.url} | LLM output truncated; try higher max_tokens.")

            if data.get("talks_about_hydrogen"):
                summary = str(data.get("summary", "")).strip()
                if summary:
                    print(f"HYDROGEN: {result.url}\nSummary: {summary}\n")
                    hits.append({"url": result.url, "summary": summary})

    llm_strategy.show_usage()
    return hits


def run_main(coro) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handler(_loop, context):
        msg = str(context.get("message", ""))
        exc = str(context.get("exception", ""))
        if "Fatal error on SSL transport" in msg or "Event loop is closed" in exc:
            return
        _loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
    try:
        loop.run_until_complete(coro)
        loop.run_until_complete(asyncio.sleep(0.3))
    finally:
        asyncio.set_event_loop(None)
        loop.close()


if __name__ == "__main__":
    test_urls = ["https://fuelcellsworks.com/2026/03/26/energy-innovation/uw-researchers-publish-article-on-hydrogen-production-using-wastewater"]
    print(f"Total URLs to crawl: {len(test_urls)}")
    run_main(crawl_hydrogen(test_urls, max_concurrent=20))