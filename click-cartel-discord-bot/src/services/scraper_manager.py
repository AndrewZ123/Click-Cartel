from __future__ import annotations
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Dict

import aiohttp
# Do NOT import Playwright at module load. Lazy-load only if enabled.
def _load_playwright():
    try:
        from playwright.async_api import async_playwright  # type: ignore
        return async_playwright
    except Exception:
        logging.getLogger(__name__).warning("Playwright not installed. PW-based scrapers disabled.")
        return None

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
        self._use_playwright_env = (os.getenv("ENABLE_PLAYWRIGHT_SCRAPERS", "true").lower() in ("1","true","yes"))
        self._async_playwright = None  # lazy

        self.scrapers: List[BaseScraper] = [
            FocusGroupsScraper(),
            # RespondentScraper(),
            # UserInterviewsScraper(),
        ]

    async def run_all(self, force: bool = False) -> Dict[str, int]:
        # Always run non-Playwright scrapers
        try:
            results = await run_scrapers(self.scrapers)
        except Exception as e:
            logger.error("run_all failed: %s", e, exc_info=True)
            results = []
        # Optionally run PW scrapers if explicitly enabled and Playwright available
        if self._use_playwright_env and self._async_playwright is None:
            self._async_playwright = _load_playwright()
        if self._use_playwright_env and self._async_playwright:
            try:
                async with self._async_playwright() as pw:  # type: ignore[misc]
                    # TODO: add PW-based scrapers here when ready
                    pass
            except Exception as e:
                logger.warning("Playwright scrapers disabled at runtime: %s", e, exc_info=True)
        return {"new": 0, "total": 0}