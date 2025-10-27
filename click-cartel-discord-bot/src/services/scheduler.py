from discord.ext import tasks
import logging
from datetime import datetime
from scrapers.site_a import SiteAScraper
from scrapers.site_b import SiteBScraper
from services.db import add_listing
from services.notifier import notify_new_listing

logging.basicConfig(level=logging.INFO)

class Scheduler:
    def __init__(self):
        self.site_a_scraper = SiteAScraper()
        self.site_b_scraper = SiteBScraper()

    @tasks.loop(minutes=10)
    async def scrape_listings(self):
        logging.info(f"Scraping listings at {datetime.now()}")
        
        site_a_listings = await self.site_a_scraper.scrape()
        site_b_listings = await self.site_b_scraper.scrape()

        all_listings = site_a_listings + site_b_listings

        for listing in all_listings:
            await add_listing(listing)
            await notify_new_listing(listing)

    def start(self):
        self.scrape_listings.start()