from __future__ import annotations
import os, sys, asyncio, logging
from pathlib import Path
from typing import Any, Optional, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

# Ensure project root (folder that contains the "src" package) is on sys.path
proj_root = Path(__file__).resolve().parents[1]  # click-cartel-discord-bot/
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Import after sys.path fix
from src.services.db import DB  # type: ignore
from src.services.scraper_manager import ScraperManager  # type: ignore

INTENTS = discord.Intents.default()
INTENTS.guilds = True

class ClickCartelBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db: Optional[DB] = None
        self.scraper_manager: Optional[ScraperManager] = None

    async def setup_hook(self) -> None:
        # DB connect
        self.db = DB(os.getenv("DB_PATH"))  # sqlite path resolved in DB class
        await self.db.connect()

        # Scraper manager
        self.scraper_manager = ScraperManager()

        # Load cogs
        for ext in (
            "src.cogs.health",
            "src.cogs.admin",
            "src.cogs.saved_searches",
            "src.cogs.rules",
        ):
            try:
                await self.load_extension(ext)
                logger.info("Loaded %s", ext)
            except Exception as e:
                logger.error("Failed to load %s: %s", ext, e, exc_info=True)

        # Sync app commands
        guild_id = int(os.getenv("GUILD_ID", "0") or 0)
        try:
            if guild_id:
                await self.tree.sync(guild=discord.Object(id=guild_id))
            else:
                await self.tree.sync()
            logger.info("Slash commands synced.")
        except Exception as e:
            logger.error("Command sync failed: %s", e, exc_info=True)

    async def on_ready(self) -> None:
        text = os.getenv("PRESENCE_TEXT", "🕵️ Paid research gigs")
        activity = discord.Game(name=text)
        try:
            await self.change_presence(status=discord.Status.online, activity=activity)
        except Exception:
            pass
        logger.info("Logged in as %s (%s)", self.user, self.user and self.user.id)

    async def perform_scrape(self, *, trigger: str, actor: Optional[int]) -> Tuple[int, int]:
        """
        Runs all scrapers and upserts into DB.
        Returns (new_rows_inserted, pending_count_after)
        """
        assert self.scraper_manager is not None, "ScraperManager missing"
        assert self.db is not None, "DB missing"
        logger.info("perform_scrape: trigger=%s actor_id=%s", trigger, actor)
        listings = await self.scraper_manager.run_all()
        new_count, pending = await self.db.upsert_listings(listings)
        logger.info("perform_scrape: new=%s pending=%s", new_count, pending)
        return new_count, pending


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")
    bot = ClickCartelBot()
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())