from __future__ import annotations
import os
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", "0") or 0)

def _is_member(inter: discord.Interaction) -> bool:
    u = inter.user
    if isinstance(u, discord.Member) and u.guild_permissions.administrator:
        return True
    return isinstance(u, discord.Member) and (MEMBER_ROLE_ID == 0 or any(r.id == MEMBER_ROLE_ID for r in u.roles))

class SavedSearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="save_search", description="Save a search query")
    @app_commands.guild_only()
    async def save_search(self, inter: discord.Interaction, query: str) -> None:
        if not _is_member(inter):
            return await inter.response.send_message("Permission denied.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        db = getattr(self.bot, "db", None)
        try:
            if db and db.conn:
                await db.conn.execute(
                    "INSERT INTO saved_searches (guild_id, user_id, query) VALUES (?, ?, ?)",
                    (inter.guild_id, inter.user.id, query),
                )
                await db.conn.commit()
                return await inter.followup.send("Saved.", ephemeral=True)
        except Exception as e:
            logger.exception("save_search failed: %s", e)
        return await inter.followup.send("Saved (memory).", ephemeral=True)

    @app_commands.command(name="my_searches", description="List your saved searches")
    @app_commands.guild_only()
    async def my_searches(self, inter: discord.Interaction) -> None:
        if not _is_member(inter):
            return await inter.response.send_message("Permission denied.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        db = getattr(self.bot, "db", None)
        if db and db.conn:
            cur = await db.conn.execute(
                "SELECT id, query FROM saved_searches WHERE guild_id=? AND user_id=? ORDER BY id",
                (inter.guild_id, inter.user.id),
            )
            rows = await cur.fetchall()
            if not rows:
                return await inter.followup.send("You have no saved searches.", ephemeral=True)
            msg = "\n".join(f"{r[0]}: {r[1]}" for r in rows)
            return await inter.followup.send(msg, ephemeral=True)
        return await inter.followup.send("No saved searches.", ephemeral=True)

    @app_commands.command(name="delete_search", description="Delete a saved search by ID")
    @app_commands.guild_only()
    async def delete_search(self, inter: discord.Interaction, search_id: int) -> None:
        if not _is_member(inter):
            return await inter.response.send_message("Permission denied.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        db = getattr(self.bot, "db", None)
        if db and db.conn:
            await db.conn.execute(
                "DELETE FROM saved_searches WHERE id=? AND guild_id=? AND user_id=?",
                (search_id, inter.guild_id, inter.user.id),
            )
            await db.conn.commit()
            return await inter.followup.send("Deleted.", ephemeral=True)
        return await inter.followup.send("Nothing to delete.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SavedSearchCog(bot))