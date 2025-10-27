from __future__ import annotations
import logging
from typing import List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, Listing

logger = logging.getLogger(__name__)


class UserInterviewsScraper(BaseScraper):
    site_name = "UserInterviews"
    requires_js = True
    list_url = "https://www.userinterviews.com/studies?study_method=online&study_state=open"

    async def scrape(self, session, page: Optional[Page]) -> List[Listing]:
        if page is None:
            logger.warning("UserInterviews requires Playwright; skipping.")
            return []

        await page.goto(self.list_url, wait_until="networkidle", timeout=60000)

        try:
            await page.locator("button:has-text('Accept')").click(timeout=3000)
        except PlaywrightTimeout:
            pass

        try:
            await page.wait_for_selector("[data-testid='study-card']", timeout=15000)
        except PlaywrightTimeout:
            logger.warning("UserInterviews cards not found.")
            return []

        while True:
            load_more = page.locator("button:has-text('Load more')")
            try:
                if await load_more.is_visible():
                    await load_more.click()
                    await page.wait_for_timeout(1500)
                else:
                    break
            except PlaywrightTimeout:
                break

        cards = page.locator("[data-testid='study-card']")
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
                    const linkNode = el.querySelector("a[href*='/projects/']");
                    return {
                        title: text("[data-testid='study-title'], h2, h3"),
                        link: linkNode ? linkNode.href : "",
                        payout: text("[data-testid='incentive-amount'], [data-testid='study-incentive']"),
                        duration: text("[data-testid='duration'], [data-testid='study-length']"),
                        method: text("[data-testid='method'], [data-testid='study-method']"),
                        deadline: text("time, [data-testid='study-deadline']"),
                        location: text("[data-testid='location'], [data-testid='study-location']"),
                        description: text("[data-testid='study-description']"),
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
                    date_posted=info["deadline"],
                    location=info["location"] or "Remote",
                    description=info["description"],
                    raw=info,
                )
            )

        logger.debug("UserInterviews parsed %d listings", len(listings))
        return listings