from __future__ import annotations
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Any, List, Optional
import os, sys, logging, asyncio, discord

# Ensure project root (the folder that contains the "src" package) is on sys.path
proj_root = Path(__file__).resolve().parents[1]  # .../click-cartel-discord-bot
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

# ---- Load .env early (supports python-dotenv; falls back to simple parser) ----
def _load_env_from_dotenv() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parent / ".env",               # src/.env
        here.parents[1] / ".env",           # repo root .env (click-cartel-discord-bot/.env)
        here.parents
    ]
    loaded = False
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
        path = find_dotenv(usecwd=True) or ""
        if not path:
            for c in candidates:
                if c.exists():
                    path = str(c)
                    break
        if path:
            load_dotenv(path, override=False)
            loaded = True
    except Exception:
        pass
    if not loaded:
        # very small .env parser
        for c in candidates:
            try:
                if not c.exists():
                    continue
                for raw in c.read_text().splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    # strip inline comments
                    if " #" in v:
                        v = v.split(" #", 1)[0].strip()
                    os.environ.setdefault(k.strip(), v)
                break
            except Exception:
                continue

_load_env_from_dotenv()

# ---- Logging ----
level_name = os.getenv("LOG_LEVEL", "INFO").upper()
level = getattr(logging, level_name, logging.INFO)
logging.basicConfig(level=level)
logging.getLogger().setLevel(level)
logger = logging.getLogger(__name__)


class ClickCartelBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.db = None
        try:
            from src.services.db import DB  # lazy import
            self.db = DB(os.getenv("DB_PATH", "clickcartel.db"))
        except Exception as e:
            logging.getLogger(__name__).warning("DB init failed: %s", e)
        try:
            from src.services.scraper_manager import ScraperManager
            self.scraper_manager = ScraperManager()
        except Exception:
            self.scraper_manager = None
        self._presence_text = os.getenv("PRESENCE_TEXT", "🕵️‍♂️ Your plug for paid research gigs.")
        self._presence_type = (os.getenv("PRESENCE_TYPE", "watching") or "watching").lower()

    def _presence_activity(self) -> discord.Activity:
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing,
        }
        atype = types.get(self._presence_type, discord.ActivityType.watching)
        return discord.Activity(type=atype, name=self._presence_text)

    async def setup_hook(self) -> None:
        if self.db:
            try:
                await self.db.connect()
            except Exception as e:
                logging.getLogger(__name__).exception("DB connect failed: %s", e)
        # load cogs
        for ext in ("src.cogs.admin", "src.cogs.saved_searches", "src.cogs.rules", "src.cogs.health"):
            try:
                await self.load_extension(ext)
            except Exception as e:
                logging.getLogger(__name__).exception("Failed to load %s: %s", ext, e)
        # Sync to guild if provided
        try:
            gid = int(os.getenv("GUILD_ID", "0") or 0)
            if gid:
                gobj = discord.Object(id=gid)
                self.tree.copy_global_to(guild=gobj)
                await self.tree.sync(guild=gobj)
                # clear globals
                self.tree.clear_commands(guild=None); await self.tree.sync()
        except Exception as e:
            logging.getLogger(__name__).debug("Command sync issue: %s", e)
        try:
            await self.change_presence(status=discord.Status.online, activity=self._presence_activity())
        except Exception:
            pass

        # Restrict member commands to a single channel (admins bypass). Default: 1432204437623148718
        MEMBER_COMMANDS_CHANNEL_ID = int(os.getenv("MEMBER_COMMANDS_CHANNEL_ID", "1432204437623148718") or 0)

        def _is_admin(user: discord.abc.User) -> bool:
            try:
                return bool(getattr(user, "guild_permissions", None) and user.guild_permissions.administrator)  # type: ignore[union-attr]
            except Exception:
                return False

        async def member_channel_guard(interaction: discord.Interaction) -> bool:
            if not interaction.guild:
                return True
            if _is_admin(interaction.user):
                return True
            if MEMBER_COMMANDS_CHANNEL_ID and interaction.channel_id != MEMBER_COMMANDS_CHANNEL_ID:
                raise app_commands.CheckFailure(f"Please use this command in <#{MEMBER_COMMANDS_CHANNEL_ID}>.")
            return True

        # Attach the guard to all app commands (works around missing CommandTree.add_check)
        for cmd in self.tree.walk_commands():
            # Avoid duplicating the check on reload
            checks = getattr(cmd, "checks", [])
            if all(getattr(c, "__name__", "") != "member_channel_guard" for c in checks):
                cmd.add_check(member_channel_guard)

    async def perform_scrape(self, *, trigger: str, actor: Optional[discord.abc.User]) -> dict:
        logger = logging.getLogger(__name__)
        logger.info("perform_scrape: trigger=%s actor_id=%s", trigger, getattr(actor, "id", None))
        if not self.scraper_manager:
            return {"total_found": 0, "new": 0, "queued": 0}
        listings = await self.scraper_manager.run_all()
        if not self.db:
            return {"total_found": len(listings), "new": 0, "queued": 0}
        upserted, pending = await self.db.upsert_listings(listings)  # type: ignore[attr-defined]
        return {"total_found": len(listings), "new": upserted, "queued": pending}

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Set DISCORD_TOKEN in .env"); return
    bot = ClickCartelBot()
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())