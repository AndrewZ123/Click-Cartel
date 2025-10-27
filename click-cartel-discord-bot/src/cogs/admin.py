from __future__ import annotations
import os
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or 0)

def _is_admin(inter: discord.Interaction) -> bool:
    u = inter.user
    return isinstance(u, discord.Member) and (u.guild_permissions.administrator or (ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in u.roles)))

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Optional loop placeholder to satisfy health check
        self.autoscrape_loop.change_interval(minutes=int(os.getenv("AUTO_SCRAPE_MINUTES", "60") or "60"))
        if not self.autoscrape_loop.is_running():
            self.autoscrape_loop.start()

    def cog_unload(self) -> None:
        if self.autoscrape_loop.is_running():
            self.autoscrape_loop.cancel()

    @tasks.loop(minutes=60.0)
    async def autoscrape_loop(self) -> None:
        # No-op placeholder
        await self._perform_scrape(trigger="auto")

    @app_commands.command(name="sync", description="Force-sync slash commands to this guild (admin)")
    @app_commands.guild_only()
    async def sync_cmd(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            g = inter.guild
            if g:
                inter.client.tree.copy_global_to(guild=g)
                synced = await inter.client.tree.sync(guild=g)
                await inter.followup.send(f"Synced {len(synced)} commands to guild {g.id}.", ephemeral=True)
            else:
                gs = await inter.client.tree.sync()
                await inter.followup.send(f"Synced {len(gs)} global commands.", ephemeral=True)
        except Exception as e:
            logger.exception("Manual sync failed")
            await inter.followup.send(f"Sync failed: {e}", ephemeral=True)

    @app_commands.command(name="scrape", description="Run scrapers now (admin)")
    @app_commands.guild_only()
    async def scrape(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        res = await self._perform_scrape(trigger="manual")
        await inter.followup.send(res, ephemeral=True)

    @app_commands.command(name="rescrape", description="Force re-scrape (admin)")
    @app_commands.guild_only()
    async def rescrape(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        res = await self._perform_scrape(trigger="manual", force=True)
        await inter.followup.send(res, ephemeral=True)

    @app_commands.command(name="db_stats", description="Show DB table counts (admin)")
    @app_commands.guild_only()
    async def db_stats(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        db = getattr(self.bot, "db", None)
        if not db or not db.conn:
            return await inter.followup.send("DB not connected.", ephemeral=True)
        try:
            rows = {}
            for table in ("listings", "posts", "rejects", "saved_searches", "auto_rules", "moderation_cards"):
                cur = await db.conn.execute(f"SELECT COUNT(*) FROM {table}")
                rows[table] = (await cur.fetchone())[0]
            lines = [f"{k}: {v}" for k, v in rows.items()]
            await inter.followup.send("DB stats:\n" + "\n".join(lines), ephemeral=True)
        except Exception as e:
            logger.exception("db_stats failed")
            await inter.followup.send(f"db_stats failed: {e}", ephemeral=True)

    @app_commands.command(name="post_listings", description="Post latest listings to the configured channel (admin)")
    @app_commands.guild_only()
    async def post_listings(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        public_channel_id = int(os.getenv("PUBLIC_CHANNEL_ID", "0") or 0)
        if not public_channel_id:
            return await inter.followup.send("PUBLIC_CHANNEL_ID not set.", ephemeral=True)
        ch = inter.client.get_channel(public_channel_id) or await inter.client.fetch_channel(public_channel_id)
        if not isinstance(ch, discord.TextChannel):
            return await inter.followup.send("Public channel not accessible.", ephemeral=True)
        await ch.send("No new listings to post right now.")
        await inter.followup.send("Posted.", ephemeral=True)

    async def _perform_scrape(self, trigger: str, force: bool = False) -> str:
        sm = getattr(self.bot, "scraper_manager", None)
        if not sm:
            return "ScraperManager not available."
        try:
            result = await sm.run_all(force=force)
            return f"Scrape complete. new={result.get('new', 0)} total={result.get('total', 0)}"
        except Exception as e:
            logger.exception("perform_scrape failed")
            return f"Scrape failed: {e}"

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))