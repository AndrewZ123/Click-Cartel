from __future__ import annotations
import os, sys, logging
from pathlib import Path
from typing import Optional, List
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Put the "src" folder on sys.path
src_root = Path(__file__).resolve().parent
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from services.db import DB  # noqa: E402
from services.scraper_manager import ScraperManager  # noqa: E402

load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True  # for role checks

class ClickCartelBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db: Optional[DB] = None
        self.scraper_manager: Optional[ScraperManager] = None

    async def setup_hook(self) -> None:
        # DB
        db_path = os.getenv("DB_PATH", "/data/clickcartel.db")
        self.db = DB(db_path)
        await self.db.connect()

        # Scrapers
        self.scraper_manager = ScraperManager()

        # Load cogs
        for ext in ("cogs.health", "cogs.admin", "cogs.saved_searches", "cogs.rules"):
            try:
                await self.load_extension(ext)
                logger.info("Loaded %s", ext)
            except Exception as e:
                logger.error("Failed to load %s: %s", ext, e, exc_info=True)

        # Register global commands (may take up to 1 hour to appear)
        try:
            gs = await self.tree.sync()
            logger.info("Global slash commands registered (%d).", len(gs))
        except Exception as e:
            logger.error("Global command sync failed: %s", e, exc_info=True)

        # Try env guild
        gid = int(os.getenv("GUILD_ID", "0") or 0)
        if gid:
            try:
                gobj = discord.Object(id=gid)
                self.tree.copy_global_to(guild=gobj)
                gsynced = await self.tree.sync(guild=gobj)
                logger.info("Env guild slash commands synced (%d) to %s.", len(gsynced), gid)
            except discord.Forbidden as e:
                logger.error("Env guild sync forbidden for %s (invite with applications.commands): %s", gid, e)
            except Exception as e:
                logger.error("Env guild sync failed for %s: %s", gid, e)

        # After ready, sync to all joined guilds
        self.loop.create_task(self._sync_to_all_guilds_after_ready())

    async def _sync_to_all_guilds_after_ready(self) -> None:
        await self.wait_until_ready()
        gids: List[int] = [g.id for g in self.guilds]
        logger.info("Syncing commands to all joined guilds: %s", gids)
        for g in self.guilds:
            try:
                self.tree.copy_global_to(guild=g)
                synced = await self.tree.sync(guild=g)
                logger.info("Synced %d commands to guild %s", len(synced), g.id)
            except Exception as e:
                logger.error("Guild %s sync failed: %s", g.id, e)

    async def on_ready(self) -> None:
        me = self.user
        guilds = ", ".join(f"{g.name}({g.id})" for g in self.guilds) or "none"
        logger.info("Logged in as %s (%s)", me, getattr(me, "id", "?"))
        logger.info("Bot is currently in guilds: %s", guilds)
        pres_text = os.getenv("PRESENCE_TEXT", "🕵️ Your plug for paid research gigs.")
        try:
            await self.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name=pres_text))
        except Exception:
            pass

def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN not set.")
        raise SystemExit(1)
    ClickCartelBot().run(token)

if __name__ == "__main__":
    main()