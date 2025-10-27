from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from ..bot import ClickCartelBot


class ListingsCog(commands.Cog):
    def __init__(self, bot: "ClickCartelBot") -> None:
        self.bot = bot

    @app_commands.command(name="listings", description="Show the latest approved focus group listings")
    async def listings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.db.fetch_recent(limit=5, approved_only=True)
        if not rows:
            await interaction.followup.send("No approved listings yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Latest Approved Listings",
            colour=discord.Colour.blue(),
        )
        for row in rows:
            embed.add_field(
                name=row["title"],
                value=(
                    f"💰 {row['payout'] or 'N/A'} • ⏱️ {row['duration'] or 'N/A'}\n"
                    f"📍 {row['location'] or 'Remote'} • 🗓️ {row['date_posted'] or 'N/A'}\n"
                    f"[View Listing]({row['link']})"
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="search", description="Search approved listings by keyword")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.db.search_listings(query, limit=5)
        if not rows:
            await interaction.followup.send(f"No approved listings found for '{query}'.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Search results for '{query}'",
            colour=discord.Colour.dark_teal(),
        )
        for row in rows:
            embed.add_field(
                name=row["title"],
                value=(
                    f"💰 {row['payout'] or 'N/A'} • ⏱️ {row['duration'] or 'N/A'}\n"
                    f"📍 {row['location'] or 'Remote'} • 🗓️ {row['date_posted'] or 'N/A'}\n"
                    f"[View Listing]({row['link']})"
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == self.bot.user.id:
            return
        if payload.guild_id != self.bot.guild_id:
            return
        if payload.emoji.name not in {"✅", "❌"}:
            return

        listing_row = await self.bot.db.get_listing_by_review_message(payload.message_id)
        if listing_row is None:
            return

        guild = self.bot.get_guild(payload.guild_id) or await self.bot.fetch_guild(payload.guild_id)
        member = payload.member or guild.get_member(payload.user_id)
        if member is None or not member.guild_permissions.administrator:
            return

        channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            message = None

        if payload.emoji.name == "✅":
            await self.bot.approve_listing(listing_row, approver=member, source_message=message)
        elif payload.emoji.name == "❌":
            await self.bot.reject_listing(listing_row, approver=member, source_message=message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ListingsCog(bot))  # type: ignore[arg-type]