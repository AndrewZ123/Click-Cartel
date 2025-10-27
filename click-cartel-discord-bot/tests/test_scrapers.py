import unittest
from src.scrapers.site_a import SiteAScraper
from src.scrapers.site_b import SiteBScraper

class TestSiteAScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SiteAScraper()

    def test_scrape_listings(self):
        listings = self.scraper.scrape_listings()
        self.assertIsInstance(listings, list)
        for listing in listings:
            self.assertIn('title', listing)
            self.assertIn('payout', listing)
            self.assertIn('link', listing)

class TestSiteBScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SiteBScraper()

    def test_scrape_listings(self):
        listings = self.scraper.scrape_listings()
        self.assertIsInstance(listings, list)
        for listing in listings:
            self.assertIn('title', listing)
            self.assertIn('payout', listing)
            self.assertIn('link', listing)

if __name__ == '__main__':
    unittest.main()