from __future__ import annotations
import os
import asyncio
import logging
from discord import app_commands
from discord.ext import commands, tasks
from io import BytesIO
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Config
        try:
            scr_int = int(os.getenv("SCRAPE_INTERVAL", "900") or "900")
        except Exception:
            scr_int = 900
        if scr_int < 900:
            logger.warning("SCRAPE_INTERVAL too low (%s). Clamping to 900s.", scr_int)
            scr_int = 900
        self._scrape_interval = scr_int
        self._auto_post = (os.getenv("AUTO_POST", "false").lower() in ("1", "true", "yes"))
        # Task state
        self._scrape_lock = asyncio.Lock()
        self.autoscrape_loop.change_interval(seconds=self._scrape_interval)

    async def cog_load(self) -> None:
        # start autoscrape loop (seconds if provided, else minutes)
        try:
            if SCRAPE_SECONDS > 0:
                self.autoscrape_loop.change_interval(seconds=SCRAPE_SECONDS)
            else:
                self.autoscrape_loop.change_interval(minutes=AUTO_MINUTES)
        except Exception:
            pass
        if not self.autoscrape_loop.is_running():
            self.autoscrape_loop.start()

    async def cog_unload(self) -> None:
        if self.autoscrape_loop.is_running():
            self.autoscrape_loop.cancel()

    @tasks.loop(seconds=900.0)
    async def autoscrape_loop(self) -> None:
        if self._scrape_lock.locked():
            logger.info("autoscrape skipped; previous run still in progress")
            return
        async with self._scrape_lock:
            await self.bot.perform_scrape(trigger="auto", actor=None)  # type: ignore[arg-type]
            if self._auto_post:
                try:
                    # Call your existing post routine if you have it; wrap to avoid crash loops
                    post_cog = self.bot.get_cog("AdminCog")
                    post_fn = getattr(post_cog, "post_unposted_listings", None)
                    if callable(post_fn):
                        await post_fn()
                except Exception as e:
                    logger.error("auto post failed: %s", e, exc_info=True)

    @autoscrape_loop.before_loop
    async def _before_autoscrape(self) -> None:
        await self.bot.wait_until_ready()

    # Optional helper you might have or add (no-op placeholder)
    async def post_unposted_listings(self) -> None:
        # Implemented elsewhere in your file; this placeholder prevents AttributeError.
        return

    # -------- Commands --------
    @app_commands.command(name="post_listings", description="Review and post unposted listings to the verified channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @require_role(ADMIN_ROLE_ID)
    async def post_listings(self, interaction: discord.Interaction) -> None:
        if not await self._safe_defer(interaction, ephemeral=True):
            return
        cid = _verified_channel_id()
        if not cid:
            await interaction.followup.send("Set PUBLIC_CHANNEL_ID (or VERIFIED_CHANNEL_ID) in .env.", ephemeral=True)
            return
        chan = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)  # type: ignore[assignment]
        if not isinstance(chan, discord.TextChannel):
            await interaction.followup.send("Verified channel not accessible.", ephemeral=True)
            return

        rows = await self._fetch_pending_rows()
        if not rows:
            await interaction.followup.send("No unposted listings. Try /scrape or /rescrape.", ephemeral=True)
            return

        rejected_links = await self._load_rejected_links()
        items: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for r in rows:
            d = _row_to_display(r)
            if not d.get("link"):
                continue
            if d["link"] in rejected_links:
                continue
            key = (d.get("site") or "", d["link"])
            if key in seen:
                continue
            seen.add(key)
            items.append(d)
        if not items:
            await interaction.followup.send("No unposted listings to review.", ephemeral=True)
            return

        view = SingleListingReviewer(items=items, target_channel=chan, bot=self.bot, author_id=interaction.user.id)
        first = view.current()
        embed = _build_listing_embed(first, 0, len(items)) if first else None
        content = f"Use ⬅️ ❌ ✅ ➡️ to review and post to {chan.mention}. Tap 🔗 Open to view the page."
        await interaction.followup.send(content, embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="rescrape", description="Clear and scrape all sources fresh")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @require_role(ADMIN_ROLE_ID)
    async def rescrape(self, interaction: discord.Interaction) -> None:
        if not await self._safe_defer(interaction, ephemeral=True):
            return
        try:
            await self.bot.db.clear_listings()  # type: ignore[attr-defined]
        except Exception as e:
            logger.exception("Failed to clear listings: %s", e)
            await interaction.followup.send("Failed to clear listings.", ephemeral=True)
            return
        summary = await self.bot.perform_scrape(trigger="rescrape", actor=interaction.user)  # type: ignore[arg-type]
        embed = discord.Embed(title="Rescrape complete",
                              colour=discord.Colour.green() if summary.get("new", 0) > 0 else discord.Colour.blurple())
        embed.add_field(name="Found", value=str(summary.get("total_found", 0)), inline=True)
        embed.add_field(name="Pending", value=str(summary.get("queued", 0)), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
        asyncio.create_task(self._announce_new_pending())

    @app_commands.command(name="scrape", description="Run scrapers and update the queue (no clear)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @require_role(ADMIN_ROLE_ID)
    async def scrape(self, interaction: discord.Interaction) -> None:
        if not await self._safe_defer(interaction, ephemeral=True):
            return
        summary = await self.bot.perform_scrape(trigger="manual", actor=interaction.user)  # type: ignore[arg-type]
        embed = discord.Embed(
            title="Scrape complete",
            colour=discord.Colour.green() if summary.get("new", 0) > 0 else discord.Colour.blurple(),
        )
        embed.add_field(name="Found", value=str(summary.get("total_found", 0)), inline=True)
        embed.add_field(name="Pending", value=str(summary.get("queued", 0)), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
        asyncio.create_task(self._announce_new_pending())

    @app_commands.command(name="db_stats", description="Show counts for listings/posts/rejects (admins)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @require_role(ADMIN_ROLE_ID)
    async def db_stats(self, interaction: discord.Interaction) -> None:
        if not await self._safe_defer(interaction, ephemeral=True):
            return
        try:
            l = (await (await self.bot.db.conn.execute("SELECT COUNT(*) FROM listings")).fetchone())[0]
            p = (await (await self.bot.db.conn.execute("SELECT COUNT(*) FROM posts")).fetchone())[0]
            r = (await (await self.bot.db.conn.execute("SELECT COUNT(*) FROM rejects")).fetchone())[0]
        except Exception as e:
            logger.exception("db_stats failed: %s", e)
            await interaction.followup.send("Failed to read counts.", ephemeral=True)
            return
        await interaction.followup.send(f"Listings: {l} • Posts: {p} • Rejects: {r}", ephemeral=True)

    # -------- Background: autoscrape, announce pending, auto-rules --------
    @tasks.loop(seconds=3600.0)
    async def autoscrape_loop(self) -> None:
        try:
            await self.bot.perform_scrape(trigger="auto", actor=None)  # type: ignore[arg-type]
        except Exception as e:
            logger.exception("auto scrape failed: %s", e)
            if ALERT_CHANNEL_ID:
                chan = self.bot.get_channel(ALERT_CHANNEL_ID)
                if isinstance(chan, discord.TextChannel):
                    await chan.send(f"Auto scrape failed: {e!r}")
        try:
            await self._auto_post_rules()
        except Exception as e:
            logger.exception("auto-post by rules failed: %s", e)
        try:
            await self._announce_new_pending()
        except Exception as e:
            logger.exception("announce pending failed: %s", e)

    async def _announce_new_pending(self) -> None:
        if not MOD_CHANNEL_ID:
            return
        chan = self.bot.get_channel(MOD_CHANNEL_ID)
        if not isinstance(chan, discord.TextChannel):
            try:
                chan = await self.bot.fetch_channel(MOD_CHANNEL_ID)  # type: ignore[assignment]
            except Exception:
                return
        if not isinstance(chan, discord.TextChannel):
            return
        # Prefer DB-filtered “unannounced” rows to avoid reposts across restarts
        rows = []
        try:
            rows = await self.bot.db.get_unannounced_pending_for_mod()  # type: ignore[attr-defined]
        except Exception:
            rows = await self._fetch_pending_rows()
        if not rows:
            return
        new_items: List[Dict[str, Any]] = []
        for r in rows:
            it = _row_to_display(r)
            link = it.get("link") or ""
            if link and link in self._announced_links:
                continue
            new_items.append(it)
        for it in new_items[:10]:
            try:
                embed = _build_listing_embed(it, 1, 1)
                embed.set_footer(text=None)
                file = None
                link_raw = it.get("link") or ""
                if "focusgroups.org" in (it.get("site") or "").lower() or "focusgroups.org" in link_raw.lower():
                    try:
                        res = await asyncio.wait_for(_focusgroups_hero_bytes(link_raw), timeout=10)
                        if res:
                            hero_bytes, hero_ext = res
                            fname = f"hero.{hero_ext}"
                            file = discord.File(BytesIO(hero_bytes), filename=fname)
                            embed.set_image(url=f"attachment://{fname}")
                    except Exception:
                        pass
                if not file and it.get("image_url"):
                    try:
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
                            async with sess.get(it["image_url"], headers={"User-Agent": "ClickCartelBot/1.0"}) as resp:
                                resp.raise_for_status()
                                data = await resp.read()
                                ctype = (resp.headers.get("Content-Type") or "").lower()
                                ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
                                fname = f"listing.{ext}"
                                file = discord.File(BytesIO(data), filename=fname)
                                embed.set_image(url=f"attachment://{fname}")
                    except Exception:
                        pass
                view = ListingModerationView(self.bot, it)
                if file:
                    msg = await chan.send(embed=embed, file=file, view=view)
                else:
                    msg = await chan.send(embed=embed, view=view)
                # Persist “announced” to survive restarts
                try:
                    if it.get("id"):
                        await self.bot.db.mark_moderation_announced(int(it["id"]), chan.id, msg.id)  # type: ignore[attr-defined]
                except Exception:
                    pass
                if it.get("link"):
                    self._announced_links.add(it["link"])
            except Exception as e:
                logger.debug("failed to announce pending: %s", e)

    async def _auto_post_rules(self) -> None:
        try:
            rules = await self.bot.db.list_rules(enabled_only=True)  # type: ignore[attr-defined]
        except Exception:
            rules = []
        if not rules:
            return
        rows = await self._fetch_pending_rows()
        if not rows:
            return
        default_cid = _verified_channel_id()
        for r in rows:
            it = _row_to_display(r)
            amt = _extract_amount_val(it.get("payout") or "")
            for rule in rules:
                d = {k: rule[k] for k in rule.keys()}
                if d.get("min_amount") is not None and (amt is None or amt < int(d["min_amount"])): continue
                if d.get("require_remote"):
                    loc = (it.get("location") or "").lower()
                    if not any(t in loc for t in ("remote", "virtual", "online", "nationwide", "national")): continue
                def contains(field: str, val: Optional[str]) -> bool:
                    if not val: return True
                    return val.lower() in (field or "").lower()
                if not contains(it.get("site"), d.get("site_contains")): continue
                if not contains(it.get("method"), d.get("method_contains")): continue
                if not contains(it.get("location"), d.get("location_contains")): continue
                chan_id = int(d.get("channel_id") or 0) or (default_cid or 0)
                if not chan_id: break
                chan = self.bot.get_channel(chan_id)
                if not isinstance(chan, discord.TextChannel): break
                embed = _build_listing_embed(it, 0, 1); embed.set_footer(text=None)
                file = None
                link_raw = it.get("link") or ""
                if "focusgroups.org" in link_raw.lower() or (it.get("site") or "").lower().startswith("focusgroups"):
                    try:
                        res = await asyncio.wait_for(_focusgroups_hero_bytes(link_raw), timeout=10)
                        if res:
                            hero_bytes, hero_ext = res
                            fname = f"hero.{hero_ext}"
                            file = discord.File(BytesIO(hero_bytes), filename=fname)
                            embed.set_image(url=f"attachment://{fname}")
                    except Exception: pass
                if not file and it.get("image_url"):
                    try:
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
                            async with sess.get(it["image_url"], headers={"User-Agent": "ClickCartelBot/1.0"}) as resp:
                                resp.raise_for_status()
                                data = await resp.read()
                                ctype = (resp.headers.get("Content-Type") or "").lower()
                                ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
                                fname = f"listing.{ext}"
                                file = discord.File(BytesIO(data), filename=fname)
                                embed.set_image(url=f"attachment://{fname}")
                    except Exception: pass
                try:
                    msg = await chan.send(embed=embed, file=file) if file else await chan.send(embed=embed)
                    if it.get("id"):
                        await self.bot.db.mark_review_posted(int(it["id"]), msg.id, msg.channel.id)  # type: ignore[arg-type]
                    self.bot.dispatch("listing_posted", it, msg)
                except Exception as e:
                    logger.debug("auto post send failed: %s", e)
                break

class SingleListingReviewer(discord.ui.View):
    def __init__(self, *, items: List[Dict[str, Any]], target_channel: discord.TextChannel,
                 bot: commands.Bot, author_id: int) -> None:
        super().__init__(timeout=600)
        self.items = items
        self.target_channel = target_channel
        self.bot = bot
        self.author_id = author_id
        self.index = 0

    def current(self) -> Optional[Dict[str, Any]]:
        return self.items[self.index] if 0 <= self.index < len(self.items) else None

    async def _refresh(self, interaction: discord.Interaction) -> None:
        it = self.current()
        if not it:
            for c in self.children:
                c.disabled = True
            try:
                await interaction.message.edit(content="Queue finished.", embed=None, view=self)
            except Exception:
                pass
            return
        try:
            embed = _build_listing_embed(it, self.index, len(self.items))
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

    def _check_author(self, interaction: discord.Interaction) -> bool:
        return int(interaction.user.id) == int(self.author_id)

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._check_author(interaction):
            await interaction.response.send_message("Not your session.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        if self.index > 0:
            self.index -= 1
        await self._refresh(interaction)

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._check_author(interaction):
            await interaction.response.send_message("Not your session.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        it = self.current()
        if it and it.get("id"):
            try:
                await self.bot.db.mark_review_rejected(int(it["id"]))  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("reject mark failed: %s", e)
        # remove from list and refresh
        if it:
            self.items.pop(self.index)
            if self.index >= len(self.items):
                self.index = max(0, len(self.items) - 1)
        await self._refresh(interaction)

    @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success)
    async def post(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._check_author(interaction):
            await interaction.response.send_message("Not your session.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        it = self.current()
        if not it:
            await interaction.followup.send("No item.", ephemeral=True); return
        # Build embed + optional image
        embed = _build_listing_embed(it, 0, 1)
        embed.set_footer(text=None)
        file = None
        link_raw = it.get("link") or ""
        if "focusgroups.org" in link_raw.lower() or (it.get("site") or "").lower().startswith("focusgroups"):
            try:
                res = await asyncio.wait_for(_focusgroups_hero_bytes(link_raw), timeout=10)
                if res:
                    hero_bytes, hero_ext = res
                    fname = f"hero.{hero_ext}"
                    file = discord.File(BytesIO(hero_bytes), filename=fname)
                    embed.set_image(url=f"attachment://{fname}")
            except Exception:
                pass
        if not file and it.get("image_url"):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
                    async with sess.get(it["image_url"], headers={"User-Agent": "ClickCartelBot/1.0"}) as resp:
                        resp.raise_for_status()
                        data = await resp.read()
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                        ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
                        fname = f"listing.{ext}"
                        file = discord.File(BytesIO(data), filename=fname)
                        embed.set_image(url=f"attachment://{fname}")
            except Exception:
                pass
        try:
            msg = await (self.target_channel.send(embed=embed, file=file) if file else self.target_channel.send(embed=embed))
            if it.get("id"):
                try:
                    await self.bot.db.mark_review_posted(int(it["id"]), msg.id, msg.channel.id)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.debug("mark_review_posted failed: %s", e)
            # Notify saved searches
            try:
                self.bot.dispatch("listing_posted", it, msg)
            except Exception:
                pass
            await interaction.followup.send(f"Posted to {self.target_channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to post: {e!r}", ephemeral=True)
            return
        # remove from list and refresh
        self.items.pop(self.index)
        if self.index >= len(self.items):
            self.index = max(0, len(self.items) - 1)
        await self._refresh(interaction)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._check_author(interaction):
            await interaction.response.send_message("Not your session.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        if self.index < len(self.items) - 1:
            self.index += 1
        await self._refresh(interaction)

    @discord.ui.button(emoji="🔗", label="Open", style=discord.ButtonStyle.secondary)
    async def open_link(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._check_author(interaction):
            await interaction.response.send_message("Not your session.", ephemeral=True); return
        it = self.current()
        url = it.get("link") if it else None
        await interaction.response.send_message(url or "No link.", ephemeral=True)

# ---- Moderation queue card (approve/reject) ----
class ListingModerationView(discord.ui.View):
    def __init__(self, bot: commands.Bot, listing: Dict[str, Any]) -> None:
        super().__init__(timeout=1800)
        self.bot = bot
        self.it = dict(listing)

    @discord.ui.button(emoji="✅", label="Approve & Post", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        chan_id = _verified_channel_id()
        if not chan_id:
            await interaction.followup.send("No verified channel configured.", ephemeral=True); return
        chan = self.bot.get_channel(chan_id)
        if not isinstance(chan, discord.TextChannel):
            await interaction.followup.send("Verified channel not accessible.", ephemeral=True); return
        # Build embed and optional image
        embed = _build_listing_embed(self.it, 1, 1)
        embed.set_footer(text=None)
        file = None
        link_raw = self.it.get("link") or ""
        if "focusgroups.org" in link_raw.lower() or (self.it.get("site") or "").lower().startswith("focusgroups"):
            try:
                res = await asyncio.wait_for(_focusgroups_hero_bytes(link_raw), timeout=10)
                if res:
                    hero_bytes, hero_ext = res
                    fname = f"hero.{hero_ext}"
                    file = discord.File(BytesIO(hero_bytes), filename=fname)
                    embed.set_image(url=f"attachment://{fname}")
            except Exception:
                pass
        if not file and self.it.get("image_url"):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
                    async with sess.get(self.it["image_url"], headers={"User-Agent": "ClickCartelBot/1.0"}) as resp:
                        resp.raise_for_status()
                        data = await resp.read()
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                        ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
                        fname = f"listing.{ext}"
                        file = discord.File(BytesIO(data), filename=fname)
                        embed.set_image(url=f"attachment://{fname}")
            except Exception:
                pass
        try:
            msg = await (chan.send(embed=embed, file=file) if file else chan.send(embed=embed))
            # Clear mod card and mark posted
            try:
                if self.it.get("id"):
                    await self.bot.db.clear_moderation_card(int(self.it["id"]))  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                if self.it.get("id"):
                    await self.bot.db.mark_review_posted(int(self.it["id"]), msg.id, msg.channel.id)  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("mark_review_posted failed: %s", e)
            try:
                self.bot.dispatch("listing_posted", self.it, msg)
            except Exception:
                pass
        except Exception as e:
            await interaction.followup.send(f"Failed to post: {e!r}", ephemeral=True); return
        # disable buttons on card
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(content="Approved ✅", view=self)
        except Exception:
            pass
        await interaction.followup.send("Posted.", ephemeral=True)

    @discord.ui.button(emoji="❌", label="Reject/Delete", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            if self.it.get("id"):
                try:
                    await self.bot.db.clear_moderation_card(int(self.it["id"]))  # type: ignore[attr-defined]
                except Exception:
                    pass
                await self.bot.db.mark_review_rejected(int(self.it["id"]))  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("mark_review_rejected failed: %s", e)
        for c in self.children:
            c.disabled = True
        try:
            await interaction.message.edit(content="Rejected ❌", view=self)
        except Exception:
            pass
        await interaction.followup.send("Rejected.", ephemeral=True)

    @discord.ui.button(emoji="🔗", label="Open", style=discord.ButtonStyle.secondary)
    async def open_link(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        url = self.it.get("link") or "No link."
        await interaction.response.send_message(url, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))