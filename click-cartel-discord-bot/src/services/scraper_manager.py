import asyncio
import logging
from dataclasses import dataclass
from typing import List, Dict

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
except ModuleNotFoundError:  # container can still run without PW
    async_playwright = None  # type: ignore[assignment]
    Browser = BrowserContext = None  # type: ignore[assignment]
    import logging as _logging
    _logging.getLogger(__name__).warning("Playwright not installed. PW-based scrapers disabled.")

from ..scrapers.base import BaseScraper, Listing, run_scrapers
from ..scrapers.focus_groups import FocusGroupsScraper
# JS scrapers are disabled until a Playwright page/context is wired into run_scrapers
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
        results = []
        # If you have scrapers that do NOT need Playwright (e.g., requests/bs4), run them always:
        # results.extend(await self._run_bs4_scrapers())
        if self._use_playwright:
            async with async_playwright() as pw:
                # ...run PW scrapers...
                pass
        return results