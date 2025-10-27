from __future__ import annotations
import os, logging, discord
from typing import Tuple, List
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency")
    @app_commands.guild_only()
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)} ms", ephemeral=True)

    @app_commands.command(name="bot_status", description="Show basic bot status")
    @app_commands.guild_only()
    async def bot_status(self, interaction: discord.Interaction) -> None:
        u = self.bot.user
        guilds = len(self.bot.guilds)
        await interaction.response.send_message(f"User: {u} ({getattr(u, 'id', '?')}) • Guilds: {guilds}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HealthCog(bot))