import asyncio
import logging
from dataclasses import dataclass
from typing import List, Dict

import aiohttp
from playwright.async_api import async_playwright, Browser, BrowserContext

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
        self.scrapers: List[BaseScraper] = [
            FocusGroupsScraper(),
            # RespondentScraper(),
            # UserInterviewsScraper(),
        ]

    async def run_all(self) -> List[Listing]:
        listings = await run_scrapers(self.scrapers)
        # De-dupe by (site, link)
        seen = set()
        unique: List[Listing] = []
        for l in listings:
            key = (l.site, l.link)
            if key in seen:
                continue
            seen.add(key)
            unique.append(l)
        logger.info("ScraperManager: %d unique listings", len(unique))
        return unique