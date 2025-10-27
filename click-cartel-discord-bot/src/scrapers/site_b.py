from bs4 import BeautifulSoup
import requests
from .base import BaseScraper

class SiteBScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.url = "https://respondent.io"

    def scrape_listings(self):
        response = self.get(self.url)
        if response:
            soup = BeautifulSoup(response, 'html.parser')
            listings = self.parse_listings(soup)
            return listings
        return []

    def parse_listings(self, soup):
        listings = []
        for item in soup.select('.listing-item'):
            title = item.select_one('.title').get_text(strip=True)
            payout = item.select_one('.payout').get_text(strip=True)
            link = item.select_one('a')['href']
            date_posted = item.select_one('.date-posted').get_text(strip=True)

            listings.append({
                'title': title,
                'payout': payout,
                'link': link,
                'date_posted': date_posted,
                'site': 'Respondent.io',
                'approved': False
            })
        return listings