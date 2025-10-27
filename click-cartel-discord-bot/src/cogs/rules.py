from __future__ import annotations
import os, logging, discord
from typing import Optional
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "951313767604584510"))

def _is_admin_perm(user: discord.abc.User) -> bool:
    try:
        return bool(getattr(user, "guild_permissions", None) and user.guild_permissions.administrator)  # type: ignore[union-attr]
    except Exception:
        return False

def require_role(role_id: int):
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.CheckFailure("Guild only.")
        if _is_admin_perm(interaction.user):
            return True
        roles = getattr(interaction.user, "roles", [])
        if not any(getattr(r, "id", None) == role_id for r in roles):  # type: ignore[attr-defined]
            raise app_commands.CheckFailure("You need the required role to use this command.")
        return True
    return app_commands.check(predicate)

class AutoRulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="rules_add", description="Add an auto-approve rule")
    @app_commands.describe(
        name="Rule name",
        min_amount="Minimum payout",
        require_remote="Only remote/virtual listings",
        site_contains="Substring in site",
        method_contains="Substring in method",
        location_contains="Substring in location",
        channel_id="Channel id to post to (defaults to verified channel)"
    )
    @require_role(ADMIN_ROLE_ID)
    async def rules_add(self, interaction: discord.Interaction, name: str, min_amount: Optional[int] = None,
                        require_remote: bool = False, site_contains: Optional[str] = None,
                        method_contains: Optional[str] = None, location_contains: Optional[str] = None,
                        channel_id: Optional[int] = None) -> None:
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Database is unavailable.", ephemeral=True); return
        rid = await self.bot.db.add_rule(name, dict(  # type: ignore[attr-defined]
            min_amount=min_amount, require_remote=require_remote, site_contains=site_contains,
            method_contains=method_contains, location_contains=location_contains, channel_id=channel_id
        ))
        await interaction.response.send_message(f"Rule {rid} added.", ephemeral=True)

    @app_commands.command(name="rules_list", description="List auto-approve rules")
    @require_role(ADMIN_ROLE_ID)
    async def rules_list(self, interaction: discord.Interaction) -> None:
        rules = await self.bot.db.list_rules()  # type: ignore[attr-defined]
        if not rules:
            await interaction.response.send_message("No rules.", ephemeral=True); return
        lines = []
        for r in rules:
            parts = []
            if r["min_amount"] is not None: parts.append(f"min ${r['min_amount']}")
            if r["require_remote"]: parts.append("remote")
            if r["site_contains"]: parts.append(f"site~{r['site_contains']}")
            if r["method_contains"]: parts.append(f"method~{r['method_contains']}")
            if r["location_contains"]: parts.append(f"loc~{r['location_contains']}")
            if r["channel_id"]: parts.append(f"->#{r['channel_id']}")
            lines.append(f"[{r['id']}] {r['name']} {' '.join(parts)} {'(enabled)' if r['enabled'] else '(disabled)'}")
        await interaction.response.send_message("\n".join(lines[:50]), ephemeral=True)

    @app_commands.command(name="rules_toggle", description="Enable/disable a rule")
    @require_role(ADMIN_ROLE_ID)
    async def rules_toggle(self, interaction: discord.Interaction, rule_id: int, enabled: bool) -> None:
        await self.bot.db.toggle_rule(int(rule_id), bool(enabled))  # type: ignore[attr-defined]
        await interaction.response.send_message("Updated.", ephemeral=True)

    @app_commands.command(name="rules_delete", description="Delete a rule")
    @require_role(ADMIN_ROLE_ID)
    async def rules_delete(self, interaction: discord.Interaction, rule_id: int) -> None:
        await self.bot.db.delete_rule(int(rule_id))  # type: ignore[attr-defined]
        await interaction.response.send_message("Deleted.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRulesCog(bot))