import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Dict

import aiohttp
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
except ModuleNotFoundError:
    async_playwright = None  # type: ignore[assignment]
    Browser = BrowserContext = None  # type: ignore[assignment]
    logging.getLogger(__name__).warning("Playwright not installed. PW-based scrapers disabled.")

from ..scrapers.base import BaseScraper, Listing, run_scrapers
from ..scrapers.focus_groups import FocusGroupsScraper
# from ..scrapers.respondent import RespondentScraper
# from ..scrapers.user_interviews import UserInterviewsScraper

logger = logging.getLogger(__name__)


@dataclass
class ScrapeSummary:
    total_found: int
    new: int
    queued: int
    errors: Dict[str, str]


class ScraperManager:
    def __init__(self) -> None:
        self._pw = None
        self._use_playwright = async_playwright is not None and (os.getenv("ENABLE_PLAYWRIGHT_SCRAPERS", "true").lower() in ("1","true","yes"))

        self.scrapers: List[BaseScraper] = [
            FocusGroupsScraper(),
            # RespondentScraper(),
            # UserInterviewsScraper(),
        ]

    async def run_all(self) -> List[Listing]:
        # Run non-Playwright scrapers (e.g., FocusGroups) unconditionally
        try:
            results = await run_scrapers(self.scrapers)
        except Exception as e:
            logger.error("run_all failed: %s", e, exc_info=True)
            results = []
        # Optionally run PW scrapers later when enabled and implemented
        return results