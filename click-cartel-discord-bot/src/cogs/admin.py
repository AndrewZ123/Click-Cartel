from __future__ import annotations
import os, logging, discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or 0)

def _is_admin(inter: discord.Interaction) -> bool:
    u = inter.user
    return isinstance(u, discord.Member) and (u.guild_permissions.administrator or (ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in u.roles)))

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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

    @app_commands.command(name="invite", description="Get the bot invite URL (admin)")
    @app_commands.guild_only()
    async def invite(self, inter: discord.Interaction) -> None:
        if not _is_admin(inter):
            return await inter.response.send_message("Admin only.", ephemeral=True)
        cid = inter.client.application_id or (getattr(inter.client.user, "id", None) or "")
        url = f"https://discord.com/api/oauth2/authorize?client_id={cid}&permissions=268437568&scope=bot%20applications.commands"
        await inter.response.send_message(url, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))