from bs4 import BeautifulSoup
import requests
from src.scrapers.base import BaseScraper
from src.models.listing import Listing

class SiteAScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.url = "https://www.userinterviews.com/"

    def scrape(self):
        response = self.get(self.url)
        if response:
            return self.parse(response.text)
        return []

    def parse(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        listings = []
        
        # Example parsing logic (this will need to be adjusted based on the actual HTML structure)
        for item in soup.select('.listing-item'):
            title = item.select_one('.title').get_text(strip=True)
            payout = item.select_one('.payout').get_text(strip=True)
            link = item.select_one('a')['href']
            date_posted = item.select_one('.date-posted').get_text(strip=True)

            listing = Listing(
                site='UserInterviews',
                title=title,
                payout=payout,
                link=link,
                date_posted=date_posted,
                approved=False
            )
            listings.append(listing)

        return listings