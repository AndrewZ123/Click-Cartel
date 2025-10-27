from __future__ import annotations
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class ScraperManager:
    async def run_all(self, force: bool = False) -> Dict[str, int]:
        logger.info("ScraperManager.run_all called (force=%s)", force)
        return {"new": 0, "total": 0}