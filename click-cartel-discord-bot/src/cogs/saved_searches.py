from __future__ import annotations
import os, re, logging, discord
from typing import Any, Dict, List, Optional
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "951313767604584510"))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", "1431403074412609576"))

def _is_admin_perm(user: discord.abc.User) -> bool:
    try:
        return bool(getattr(user, "guild_permissions", None) and user.guild_permissions.administrator)  # type: ignore[union-attr]
    except Exception:
        return False

def require_any_role(*role_ids: int):
    ids = set(role_ids)
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.CheckFailure("Guild only.")
        if _is_admin_perm(interaction.user):
            return True
        roles = getattr(interaction.user, "roles", [])
        if not any(getattr(r, "id", None) in ids for r in roles):  # type: ignore[attr-defined]
            raise app_commands.CheckFailure("You need the required role to use this command.")
        return True
    return app_commands.check(predicate)

def _build_listing_embed(it: Dict[str, Any] | None, idx: int = 0, total: int = 1) -> discord.Embed:
    it = it or {}
    title = it.get("title") or "(untitled)"
    link = it.get("link") or None
    embed = discord.Embed(
        title=title,
        url=link,
        description=(
            f"💰 {it.get('payout') or 'N/A'} • 🗓️ {it.get('date_posted') or 'N/A'}\n"
            f"📍 {it.get('location') or 'Remote'} • 🏷️ {it.get('site') or ''} • 🧪 {it.get('method') or ''}"
        ),
        colour=discord.Colour.blue(),
    )
    img = it.get("image_url") or ""
    if img:
        embed.set_image(url=img)
    embed.set_footer(text=f"{idx + 1} of {total}")
    return embed

def _extract_amount_val(payout: str) -> Optional[int]:
    if not payout:
        return None
    nums = []
    for m in re.findall(r"\$?\s*([\d,]+)(?:\.\d{2})?", payout):
        try:
            nums.append(int(m.replace(",", "")))
        except Exception:
            pass
    return max(nums) if nums else None

def _jump_url(msg: discord.Message) -> Optional[str]:
    try:
        gid = getattr(msg.guild, "id", None)
        if not gid:
            return None
        return f"https://discord.com/channels/{gid}/{msg.channel.id}/{msg.id}"
    except Exception:
        return None

class SavedSearchLinksView(discord.ui.View):
    def __init__(self, *, listing_url: Optional[str], jump_url: Optional[str]) -> None:
        super().__init__(timeout=0)
        if listing_url:
            self.add_item(discord.ui.Button(emoji="🔗", label="Open Listing", style=discord.ButtonStyle.link, url=listing_url))
        if jump_url:
            self.add_item(discord.ui.Button(emoji="🧵", label="View in Server", style=discord.ButtonStyle.link, url=jump_url))

class SavedSearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _match(self, data: Dict[str, Any], params: Dict[str, Any]) -> bool:
        title = (data.get("title") or "").lower()
        desc = (data.get("description") or "").lower()
        loc = (data.get("location") or "").lower()
        site = (data.get("site") or "").lower()
        method = (data.get("method") or "").lower()
        q = params.get("q")
        if q:
            terms = [t.strip().lower() for t in str(q).split() if t.strip()]
            if not all(any(term in title or term in desc for term in [term]) for term in terms):
                return False
        min_amount = params.get("min_amount")
        if min_amount is not None:
            amt = _extract_amount_val(data.get("payout") or "")
            if not (amt is not None and amt >= int(min_amount)):
                return False
        loc_q = (params.get("location") or "").lower().strip()
        if loc_q:
            if loc_q in ("remote", "virtual", "online", "nationwide", "national"):
                if not any(t in loc for t in ("remote", "virtual", "online", "nationwide", "national")):
                    return False
            elif loc_q not in loc:
                return False
        if params.get("method") and str(params["method"]).lower() not in method:
            return False
        if params.get("site") and str(params["site"]).lower() not in site:
            return False
        if params.get("remote_only"):
            if not any(t in loc for t in ("remote", "virtual", "online", "nationwide", "national")):
                return False
        return True

    @commands.Cog.listener()
    async def on_listing_posted(self, listing: Dict[str, Any], message: discord.Message) -> None:
        try:
            searches = await self.bot.db.iter_saved_searches()  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("iter_saved_searches failed: %s", e); return
        jump = _jump_url(message)
        for s in searches:
            params = {k: s[k] for k in s.keys()}
            if not self._match(listing, params):
                continue
            user = self.bot.get_user(int(s["user_id"])) or (await self.bot.fetch_user(int(s["user_id"])))
            if not user:
                continue
            try:
                embed = _build_listing_embed(listing, 0, 1)
                embed.set_footer(text=f"Saved search • {s['name']}")
                view = SavedSearchLinksView(listing_url=listing.get("link") or None, jump_url=jump)
                await user.send(f"🔔 A new listing matches your saved search “{s['name']}”.", embed=embed, view=view)
            except Exception as e:
                logger.debug("dm failed: %s", e)

    @app_commands.command(name="save_search", description="Save a search and get DM alerts when matches are posted")
    @app_commands.guild_only()
    @require_any_role(MEMBER_ROLE_ID, ADMIN_ROLE_ID)
    async def save_search(self, interaction: discord.Interaction, name: str, q: Optional[str] = None,
                          min_amount: Optional[int] = None, location: Optional[str] = None,
                          method: Optional[str] = None, site: Optional[str] = None, remote_only: bool = False) -> None:
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Database is unavailable.", ephemeral=True); return
        params = dict(q=q, min_amount=min_amount, location=location, method=method, site=site, remote_only=remote_only)
        sid = await self.bot.db.add_saved_search(interaction.user.id, name, params)  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Saved search “{name}” (id {sid}). You’ll get DMs on matches.", ephemeral=True)

    @app_commands.command(name="my_searches", description="List your saved searches")
    @app_commands.guild_only()
    @require_any_role(MEMBER_ROLE_ID, ADMIN_ROLE_ID)
    async def my_searches(self, interaction: discord.Interaction) -> None:
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Database is unavailable.", ephemeral=True); return
        rows = await self.bot.db.list_saved_searches(interaction.user.id)  # type: ignore[attr-defined]
        if not rows:
            await interaction.response.send_message("You have no saved searches.", ephemeral=True); return
        lines = []
        for r in rows[:20]:
            desc = []
            if r["q"]: desc.append(f'“{r["q"]}”')
            if r["min_amount"] is not None: desc.append(f"min ${r['min_amount']}")
            if r["location"]: desc.append(r["location"])
            if r["method"]: desc.append(r["method"])
            if r["site"]: desc.append(f"on {r['site']}")
            if r["remote_only"]: desc.append("(Remote)")
            lines.append(f"- [{r['id']}] {r['name']}: " + ", ".join(desc) if desc else f"- [{r['id']}] {r['name']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="delete_search", description="Delete a saved search by id")
    @app_commands.guild_only()
    @require_any_role(MEMBER_ROLE_ID, ADMIN_ROLE_ID)
    async def delete_search(self, interaction: discord.Interaction, search_id: int) -> None:
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Database is unavailable.", ephemeral=True); return
        await self.bot.db.delete_saved_search(interaction.user.id, int(search_id))  # type: ignore[attr-defined]
        await interaction.response.send_message("Deleted.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SavedSearchCog(bot))