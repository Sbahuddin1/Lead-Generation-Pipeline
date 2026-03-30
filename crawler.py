import asyncio
from typing import Awaitable, Callable, Dict, List, Optional
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    UndetectedAdapter,
    CrawlResult,
)
from crawl4ai.async_dispatcher import SemaphoreDispatcher
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai import ProxyConfig, RateLimiter, CrawlerMonitor


async def parallel_crawl(
    urls: List[str],
    max_concurrent: int = 8,
    process_result: Optional[Callable[[CrawlResult], Awaitable[None]]] = None,
    use_undetected: bool = True,
    headless: bool = True,
    proxy_chain: Optional[List[ProxyConfig]] = None,
    fallback_fetch_function: Optional[Callable[[str], Awaitable[str]]] = None,
) -> List[CrawlResult]:
    """
    Fast parallel crawler with layered anti-bot protection.

    Docs-aligned behavior:
    - Uses fixed-concurrency dispatcher for predictable throughput.
    - Enables anti-bot retries/proxy escalation via CrawlerRunConfig.
    - Uses UndetectedAdapter (optional) instead of unsupported browser_type values.
    """

    if not urls:
        return []

    max_concurrent = max(1, max_concurrent)

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=headless,
        enable_stealth=True,
        user_agent_mode="random",
        light_mode=True,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        # crawl4ai 0.8.6: SemaphoreDispatcher supports run_urls (batch) but not run_urls_stream.
        stream=False,
        magic=True,
        simulate_user=True,
        remove_overlay_elements=True,
        wait_until="load",
        page_timeout=60000,
        delay_before_return_html=0.6,
        max_retries=1,
        proxy_config=proxy_chain,
        fallback_fetch_function=fallback_fetch_function,
    )

    dispatcher = SemaphoreDispatcher(
        max_session_permit=max_concurrent,
        rate_limiter=RateLimiter(
            base_delay=(0.2, 0.8),
            max_delay=8.0,
            max_retries=2,
            rate_limit_codes=[429, 503],
        ),
        monitor=CrawlerMonitor(
            urls_total=len(urls),
            refresh_rate=1.0,
            enable_ui=True,
            max_width=120,
        ),
    )

    crawler_kwargs = {"config": browser_config}
    if use_undetected:
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            browser_adapter=UndetectedAdapter(),
        )
        crawler_kwargs["crawler_strategy"] = crawler_strategy

    collected: List[CrawlResult] = []

    async with AsyncWebCrawler(**crawler_kwargs) as crawler:
        print(
            f"Starting crawl on {len(urls)} URLs "
            f"(max_concurrent={max_concurrent}, undetected={use_undetected})"
        )

        results = await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher,
        )

        for result in results:
            collected.append(result)

            if result.success:
                markdown_len = len(getattr(result, "markdown", "") or "")
                print(f"OK: {result.url} | content={markdown_len:,} chars")
                if process_result is not None:
                    await process_result(result)
            else:
                reason = str(result.error_message or "Unknown error")[:180]
                print(f"FAIL: {result.url} | {reason}")

    print("Crawl finished.")
    return collected


async def _print_excerpt(result: CrawlResult) -> None:
    text = (getattr(result, "markdown", "") or "").strip().replace("\n", " ")
    print(f"Excerpt: {text[:120]}")


def _get_full_markdown(result: CrawlResult) -> str:
    """Return the full markdown payload from a CrawlResult."""
    markdown_obj = getattr(result, "markdown", "")
    raw_markdown = getattr(markdown_obj, "raw_markdown", None)
    if isinstance(raw_markdown, str) and raw_markdown:
        return raw_markdown
    return str(markdown_obj or "")


async def scrape_pages_fully(
    urls: List[str],
    max_concurrent: int = 8,
    use_undetected: bool = True,
    headless: bool = True,
) -> List[Dict[str, str]]:
    """Scrape each URL and return full page content.

    Returns one entry per URL with full markdown and HTML.
    """
    results = await parallel_crawl(
        urls=urls,
        max_concurrent=max_concurrent,
        process_result=None,
        use_undetected=use_undetected,
        headless=headless,
    )

    pages: List[Dict[str, str]] = []
    for result in results:
        if not result.success:
            continue

        pages.append(
            {
                "url": result.url,
                "markdown": _get_full_markdown(result),
                "html": str(getattr(result, "html", "") or ""),
            }
        )

    return pages


# ====================== TEST EXECUTION ======================
if __name__ == "__main__":
    test_urls = [
        "https://fuelcellsworks.com/2026/03/26/energy-innovation/uw-researchers-publish-article-on-hydrogen-production-using-wastewater",       # Add more as needed
    ]

    print(f"Total URLs to crawl: {len(test_urls)}")

    try:
        pages = asyncio.run(
            scrape_pages_fully(
                test_urls,
                max_concurrent=6,
                use_undetected=True,
                headless=True,
            )
        )
        for page in pages:
            print(f"\nURL: {page['url']}")
            print("\n=== FULL MARKDOWN ===\n")
            print(page["markdown"])
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")