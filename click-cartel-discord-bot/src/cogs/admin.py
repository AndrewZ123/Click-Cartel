from __future__ import annotations
import os
import asyncio
import logging
from typing import Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # SCRAPE_INTERVAL minimum 900s (15 min)
        try:
            interval = int(os.getenv("SCRAPE_INTERVAL", "900") or "900")
        except Exception:
            interval = 900
        if interval < 900:
            logger.warning("SCRAPE_INTERVAL too low (%s). Clamping to 900s.", interval)
            interval = 900
        self._interval = interval
        self._lock = asyncio.Lock()
        self.autoscrape_loop.change_interval(seconds=self._interval)

    async def cog_load(self) -> None:
        if not self.autoscrape_loop.is_running():
            self.autoscrape_loop.start()

    async def cog_unload(self) -> None:
        if self.autoscrape_loop.is_running():
            self.autoscrape_loop.cancel()

    @tasks.loop(seconds=900.0)
    async def autoscrape_loop(self) -> None:
        if self._lock.locked():
            logger.info("autoscrape skipped; previous run still in progress")
            return
        async with self._lock:
            try:
                await self._do_scrape(trigger="auto")
            except Exception as e:
                logger.error("auto scrape failed: %s", e, exc_info=True)

    @autoscrape_loop.before_loop
    async def _before_autoscrape(self) -> None:
        await self.bot.wait_until_ready()

    async def _do_scrape(self, *, trigger: str) -> Tuple[int, int]:
        # Runs bot.perform_scrape if available
        if hasattr(self.bot, "perform_scrape"):
            return await self.bot.perform_scrape(trigger=trigger, actor=None)  # type: ignore
        raise RuntimeError("perform_scrape not available on bot")

    # Slash commands (admin-only)
    @app_commands.command(name="scrape", description="Run scrapers and update the queue (no clear)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def scrape_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            new_count, pending = await self._do_scrape(trigger="manual")
            await interaction.followup.send(f"Scrape done. New: {new_count}, Pending: {pending}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Scrape failed: {e!r}", ephemeral=True)

    @app_commands.command(name="rescrape", description="Clear and scrape all sources fresh")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def rescrape_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            db = getattr(self.bot, "db", None)
            if not db:
                await interaction.followup.send("DB not available.", ephemeral=True); return
            await db.clear_listings()  # type: ignore
            new_count, pending = await self._do_scrape(trigger="rescrape")
            await interaction.followup.send(f"Rescrape done. New: {new_count}, Pending: {pending}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Rescrape failed: {e!r}", ephemeral=True)

    @app_commands.command(name="post_listings", description="Post pending listings (simple batch)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def post_listings_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            # Minimal placeholder to satisfy command presence; integrate your posting flow here.
            await interaction.followup.send("Posting flow not configured yet.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Post failed: {e!r}", ephemeral=True)

    @app_commands.command(name="db_stats", description="Show counts for listings/posts/rejects")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def db_stats_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        db = getattr(self.bot, "db", None)
        if not db or not getattr(db, "conn", None):
            await interaction.followup.send("DB not available.", ephemeral=True); return
        try:
            conn = db.conn  # type: ignore
            c1 = await conn.execute("SELECT COUNT(*) FROM listings"); n_list = (await c1.fetchone())[0]
            c2 = await conn.execute("SELECT COUNT(*) FROM posts"); n_posts = (await c2.fetchone())[0]
            c3 = await conn.execute("SELECT COUNT(*) FROM rejects"); n_rej = (await c3.fetchone())[0]
            await interaction.followup.send(f"DB stats — listings: {n_list}, posted: {n_posts}, rejects: {n_rej}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"DB stats failed: {e!r}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))