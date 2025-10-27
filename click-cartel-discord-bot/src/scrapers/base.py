from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Listing:
    source: str
    title: str
    url: str
    pay: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseScraper:
    site_name: str = "base"
    requires_js: bool = False

    async def fetch(self) -> List[Listing]:
        return []

async def run_scrapers(scrapers: List[BaseScraper]) -> List[Listing]:
    out: List[Listing] = []
    for s in scrapers:
        try:
            out.extend(await s.fetch())
        except Exception:
            logger.exception("Scraper %s failed", s.site_name)
    return out