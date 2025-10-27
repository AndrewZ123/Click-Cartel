from discord.ext import commands
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def bot():
    bot = commands.Bot(command_prefix='!')
    return bot

@pytest.fixture
def listings_cog(bot):
    from src.cogs.listings import ListingsCog
    cog = ListingsCog(bot)
    bot.add_cog(cog)
    return cog

@pytest.fixture
def admin_cog(bot):
    from src.cogs.admin import AdminCog
    cog = AdminCog(bot)
    bot.add_cog(cog)
    return cog

@pytest.mark.asyncio
async def test_scrape_command(listings_cog):
    with patch('src.scrapers.site_a.SiteAScraper.scrape', new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = [{'title': 'Test Listing', 'link': 'http://example.com', 'payout': '$50'}]
        await listings_cog.scrape(ctx=AsyncMock())
        listings = await listings_cog.get_listings()
        assert len(listings) == 1
        assert listings[0]['title'] == 'Test Listing'

@pytest.mark.asyncio
async def test_approve_command(admin_cog):
    with patch('src.services.db.approve_listing', new_callable=AsyncMock) as mock_approve:
        mock_approve.return_value = True
        result = await admin_cog.approve(ctx=AsyncMock(), listing_id=1)
        assert result is True
        mock_approve.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_status_command(admin_cog):
    with patch('src.services.db.get_status', new_callable=AsyncMock) as mock_get_status:
        mock_get_status.return_value = {'active_listings': 5, 'approved_listings': 3}
        response = await admin_cog.status(ctx=AsyncMock())
        assert 'Active Listings: 5' in response.content
        assert 'Approved Listings: 3' in response.content