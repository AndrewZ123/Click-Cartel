from __future__ import annotations
import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or 0)

def _is_admin(inter: discord.Interaction) -> bool:
    u = inter.user
    return isinstance(u, discord.Member) and (u.guild_permissions.administrator or (ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in u.roles)))

class AutoRulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="rules_add", description="Add an auto rule (admin)")
    @app_commands.guild_only()
    async def rules_add(self, inter: discord.Interaction, name: str, query: str) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.send_message(f"Rule '{name}' added with query: {query}", ephemeral=True)

    @app_commands.command(name="rules_list", description="List auto rules (admin)")
    @app_commands.guild_only()
    async def rules_list(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.send_message("No rules configured.", ephemeral=True)

    @app_commands.command(name="rules_toggle", description="Enable/disable a rule (admin)")
    @app_commands.guild_only()
    async def rules_toggle(self, inter: discord.Interaction, name: str) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.send_message(f"Toggled rule '{name}'.", ephemeral=True)

    @app_commands.command(name="rules_delete", description="Delete a rule (admin)")
    @app_commands.guild_only()
    async def rules_delete(self, inter: discord.Interaction, name: str) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        await inter.response.send_message(f"Deleted rule '{name}'.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRulesCog(bot))