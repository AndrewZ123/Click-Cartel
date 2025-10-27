from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import hashlib

import aiohttp
from aiohttp import ClientResponseError, ContentTypeError

logger = logging.getLogger(__name__)


@dataclass
class Listing:
    site: str
    title: str
    link: str
    payout: str = ""
    date_posted: str = ""
    location: str = ""
    method: str = ""
    description: str = ""
    image_url: str = ""  # NEW

    def __post_init__(self) -> None:
        identity = f"{self.site}|{self.title}|{self.link}"
        self.id = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def to_db_tuple(self) -> tuple:
        return (
            self.id,
            self.site,
            self.title,
            self.payout,
            self.link,
            self.date_posted,
            self.location,
            self.method,
            self.description,
        )


class BaseScraper:
    site_name: str = "Unknown"
    request_delay: float = 1.0
    requires_js: bool = False

    async def fetch_text(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> str:
        await asyncio.sleep(self.request_delay)
        async with session.get(url, headers=headers or {}, params=params or {}) as response:
            response.raise_for_status()
            return await response.text()

    async def fetch_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict:
        await asyncio.sleep(self.request_delay)
        async with session.get(url, headers=headers or {}, params=params or {}) as response:
            response.raise_for_status()
            try:
                return await response.json()
            except ContentTypeError:
                text = await response.text()
                logger.debug("Expected JSON but got text for %s: %s", url, text[:200])
                raise

    async def scrape(
        self,
        session: aiohttp.ClientSession,
        page: Optional["Page"] = None,
    ) -> List[Listing]:
        raise NotImplementedError("Scrapers must implement scrape()")


async def run_scrapers(scrapers: List[BaseScraper]) -> List[Listing]:
    # Shorter total timeout so commands stay responsive
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        results: List[Listing] = []
        tasks = [s.scrape(session) for s in scrapers]
        scraped = await asyncio.gather(*tasks, return_exceptions=True)
        for res in scraped:
            if isinstance(res, Exception):
                logger.exception("Scraper failed", exc_info=res)
                continue
            results.extend(res or [])
        return results