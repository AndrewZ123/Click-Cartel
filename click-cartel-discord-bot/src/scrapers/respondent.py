from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, Listing

logger = logging.getLogger(__name__)


class RespondentScraper(BaseScraper):
    site_name = "Respondent"
    requires_js = True
    list_url = "https://respondent.io/research-projects"

    async def scrape(self, session, page: Optional[Page]) -> List[Listing]:
        if page is None:
            logger.warning("Respondent requires Playwright; skipping.")
            return []

        await page.goto(self.list_url, wait_until="networkidle", timeout=60000)

        try:
            await page.locator("button:has-text('Accept All')").click(timeout=3000)
        except PlaywrightTimeout:
            pass

        for _ in range(5):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(500)

        try:
            await page.wait_for_selector("[data-testid='project-card'], a[href*='/project/']", timeout=15000)
        except PlaywrightTimeout:
            logger.warning("Respondent cards not visible; trying bootstrap data.")
            payload = await page.evaluate("() => window.__NEXT_DATA__")
            return self._parse_bootstrap(payload)

        cards = page.locator("[data-testid='project-card'], a[href*='/project/']")
        count = await cards.count()
        listings: List[Listing] = []
        for idx in range(count):
            card = cards.nth(idx)
            info = await card.evaluate(
                """el => {
                    const text = sel => {
                        const node = el.querySelector(sel);
                        return node ? node.textContent.trim() : "";
                    };
                    const link = el.href || (el.querySelector("a") ? el.querySelector("a").href : "");
                    return {
                        title: text("h2, h3"),
                        link,
                        payout: text("[data-testid='reward'], [class*='Reward']"),
                        duration: text("[data-testid='duration'], [class*='Duration']"),
                        method: text("[data-testid='method'], [class*='Method']"),
                        location: text("[data-testid='location'], [class*='Location']"),
                        posted: text("time"),
                    };
                }"""
            )
            if not info["title"] or not info["link"]:
                continue
            listings.append(
                Listing(
                    site=self.site_name,
                    title=info["title"],
                    link=info["link"],
                    payout=info["payout"],
                    duration=info["duration"],
                    method=info["method"],
                    location=info["location"] or "Remote",
                    date_posted=info["posted"],
                    raw=info,
                )
            )

        if not listings:
            payload = await page.evaluate("() => window.__NEXT_DATA__")
            listings = self._parse_bootstrap(payload)

        logger.debug("Respondent parsed %d listings", len(listings))
        return listings

    def _parse_bootstrap(self, payload: Any) -> List[Listing]:
        if not isinstance(payload, dict):
            return []
        node: Any = payload
        for key in ("props", "pageProps", "pageData", "results"):
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
        projects = node if isinstance(node, list) else []
        listings: List[Listing] = []
        for project in projects:
            if not isinstance(project, dict):
                continue
            title = (project.get("name") or project.get("title") or "").strip()
            link = (project.get("public_url") or project.get("url") or "").strip()
            if not title or not link:
                continue
            payout = project.get("reward") or ""
            duration = project.get("length") or ""
            method = project.get("method") or ""
            location = project.get("location", "Remote")
            listings.append(
                Listing(
                    site=self.site_name,
                    title=title,
                    link=link,
                    payout=str(payout).strip(),
                    duration=str(duration).strip(),
                    method=str(method).strip(),
                    location=str(location).strip(),
                    date_posted=str(project.get("published_at") or ""),
                    raw=project,
                )
            )
        return listings