from __future__ import annotations
import os
import logging
import math
import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

BOT_STATUS_CHANNEL_ID = int(os.getenv("BOT_STATUS_CHANNEL_ID", "1432199680137363476") or "0")

class DiscordErrorReporter(logging.Handler):
    """Send ERROR logs to the status channel immediately."""
    def __init__(self, cog: "HealthCog") -> None:
        super().__init__(level=logging.ERROR)
        self.cog = cog
        self.bot = cog.bot
        self.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
        self._last_key: str | None = None
        self._last_ts: float = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            loop = self.bot.loop
            # Dedup identical errors within 10s
            key = f"{record.name}:{record.levelno}:{record.getMessage()}"
            now = loop.time() if loop.is_running() else 0.0
            if self._last_key == key and now and (now - self._last_ts) < 10.0:
                return
            self._last_key, self._last_ts = key, now
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._send(record)))
        except Exception:
            pass

    async def _send(self, record: logging.LogRecord) -> None:
        try:
            await self.bot.wait_until_ready()
            chan = await self.cog._resolve_status_channel()
            if not chan:
                return
            title = "Bot Error"
            colour = discord.Colour.red()
            desc = f"{record.levelname} in {record.name}"
            msg_text = ""
            try:
                msg_text = record.getMessage()
            except Exception:
                msg_text = str(record.msg)
            embed = discord.Embed(title=title, description=desc, colour=colour, timestamp=datetime.now(timezone.utc))
            if msg_text:
                txt = msg_text
                if len(txt) > 1024:
                    txt = txt[:1021] + "..."
                embed.add_field(name="Message", value=f"```text\n{txt}\n```", inline=False)
            if record.exc_info:
                tb = "".join(traceback.format_exception(*record.exc_info))
                if len(tb) > 3900:
                    tb = tb[-3900:]
                embed.add_field(name="Traceback", value=f"```text\n{tb}\n```", inline=False)
            elif record.stack_info:
                si = str(record.stack_info)
                if len(si) > 3900:
                    si = si[-3900:]
                embed.add_field(name="Stack", value=f"```text\n{si}\n```", inline=False)
            await chan.send(embed=embed)
        except Exception:
            pass

class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._health_loop.change_interval(seconds=10800)
        self._log_handler: DiscordErrorReporter | None = None

    async def cog_load(self) -> None:
        # Attach reporter once (target all logs; change "logging.getLogger('src')" to limit scope)
        if not self._log_handler:
            self._log_handler = DiscordErrorReporter(self)
            logging.getLogger().addHandler(self._log_handler)
        if not self._health_loop.is_running():
            self._health_loop.start()

    async def cog_unload(self) -> None:
        if self._health_loop.is_running():
            self._health_loop.cancel()
        if self._log_handler:
            try:
                logging.getLogger().removeHandler(self._log_handler)
            except Exception:
                pass
            self._log_handler = None

    @tasks.loop(seconds=10800.0)
    async def _health_loop(self) -> None:
        try:
            await self._send_status_embed()
        except Exception as e:
            logger.exception("scheduled health report failed: %s", e)

    @_health_loop.before_loop
    async def _before_health_loop(self) -> None:
        # Ready, send one immediately, then wait 3h to avoid double
        await self.bot.wait_until_ready()
        try:
            await self._send_status_embed()
        except Exception as e:
            logger.debug("initial health report failed: %s", e)
        await asyncio.sleep(10800.0)

    async def _send_status_embed(self) -> None:
        embed, _ok = await self._build_status_embed()
        chan = await self._resolve_status_channel()
        if not chan:
            logger.warning("Bot status channel not found or inaccessible (BOT_STATUS_CHANNEL_ID=%s).", BOT_STATUS_CHANNEL_ID)
            return
        await chan.send(embed=embed)

    async def _resolve_status_channel(self) -> discord.TextChannel | None:
        if not BOT_STATUS_CHANNEL_ID:
            return None
        ch = self.bot.get_channel(BOT_STATUS_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            ch = await self.bot.fetch_channel(BOT_STATUS_CHANNEL_ID)
        except Exception:
            return None
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _build_status_embed(self) -> Tuple[discord.Embed, bool]:
        checks: List[Tuple[str, bool, str]] = []

        # 1) Gateway/Latency
        try:
            lat = float(self.bot.latency or 0.0)
            connected = (not self.bot.is_closed()) and (self.bot.user is not None)
            detail = "Latency: unknown" if not math.isfinite(lat) or lat < 0 else f"Latency: {int(lat * 1000)} ms"
            checks.append(("Gateway/Latency", connected, detail))
        except Exception as e:
            checks.append(("Gateway/Latency", False, f"Error: {e!r}"))

        # 2) DB
        try:
            if getattr(self.bot, "db", None) and getattr(self.bot.db, "conn", None):
                await self.bot.db.conn.execute("SELECT 1")  # type: ignore[attr-defined]
                needed = {"listings", "posts", "rejects", "saved_searches", "auto_rules", "moderation_cards"}
                cur = await self.bot.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")  # type: ignore[attr-defined]
                names = {row[0] for row in await cur.fetchall()}
                missing = sorted(list(needed - names))
                checks.append(("DB connection", True, "OK"))
                checks.append(("DB schema", len(missing) == 0, "OK" if not missing else f"Missing tables: {', '.join(missing)}"))
            else:
                checks.append(("DB connection", False, "No DB or not connected"))
        except Exception as e:
            checks.append(("DB", False, f"Error: {e!r}"))

        # 3) Cogs
        try:
            cog_names = ["AdminCog", "SavedSearchCog", "AutoRulesCog"]
            missing = [n for n in cog_names if self.bot.get_cog(n) is None]
            checks.append(("Cogs", len(missing) == 0, "Loaded: " + ", ".join([n for n in cog_names if n not in missing]) + ("" if not missing else f" | Missing: {', '.join(missing)}")))
        except Exception as e:
            checks.append(("Cogs", False, f"Error: {e!r}"))

        # 4) Slash commands (global + guild)
        try:
            expected = {"scrape", "rescrape", "post_listings", "db_stats", "save_search", "my_searches", "delete_search", "rules_add", "rules_list", "rules_toggle", "rules_delete", "bot_status"}
            present: set[str] = set()
            try:
                present |= {c.name for c in self.bot.tree.get_commands()}
            except Exception:
                pass
            gid = int(os.getenv("GUILD_ID", "0") or 0)
            if gid:
                gobj = discord.Object(id=gid)
                try:
                    present |= {c.name for c in self.bot.tree.get_commands(guild=gobj)}
                except Exception:
                    pass
                try:
                    fetched = await self.bot.tree.fetch_commands(guild=gobj)
                    present |= {c.name for c in fetched}
                except Exception:
                    pass
            missing = expected - present
            checks.append(("Slash commands", len(missing) == 0, "OK" if not missing else f"Missing: {', '.join(sorted(missing))}"))
        except Exception as e:
            checks.append(("Slash commands", False, f"Error: {e!r}"))

        # 5) Channels
        try:
            ids = {
                "Public": int(os.getenv("PUBLIC_CHANNEL_ID", "0") or 0),
                "Review": int(os.getenv("REVIEW_CHANNEL_ID", os.getenv("MOD_CHANNEL_ID", "0") or "0") or 0),
                "Status": BOT_STATUS_CHANNEL_ID,
            }
            problems: List[str] = []
            ok_count = 0
            for label, cid in ids.items():
                if not cid:
                    problems.append(f"{label}: unset")
                    continue
                ch = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
                if not isinstance(ch, discord.TextChannel):
                    problems.append(f"{label}: not a text channel or inaccessible")
                    continue
                me = getattr(ch.guild, "me", None)
                if me:
                    perms = ch.permissions_for(me)
                    if not perms.send_messages or not perms.embed_links:
                        problems.append(f"{label}: missing send/embed perms")
                        continue
                ok_count += 1
            checks.append(("Channels", len(problems) == 0, f"OK ({ok_count} reachable)" if not problems else "; ".join(problems)))
        except Exception as e:
            checks.append(("Channels", False, f"Error: {e!r}"))

        # 6) Background loop
        try:
            admin = self.bot.get_cog("AdminCog")
            loop_ok = bool(getattr(admin, "autoscrape_loop", None) and getattr(admin.autoscrape_loop, "is_running", lambda: False)())
            checks.append(("Autoscrape loop", loop_ok, "Running" if loop_ok else "Not running"))
        except Exception as e:
            checks.append(("Autoscrape loop", False, f"Error: {e!r}"))

        # 7) Scraper manager presence
        try:
            sm = getattr(self.bot, "scraper_manager", None)
            ok_sm = sm is not None and hasattr(sm, "run_all")
            checks.append(("ScraperManager", ok_sm, "Available" if ok_sm else "Missing"))
        except Exception as e:
            checks.append(("ScraperManager", False, f"Error: {e!r}"))

        all_ok = all(ok for _, ok, _ in checks)
        colour = discord.Colour.green() if all_ok else discord.Colour.red()
        embed = discord.Embed(
            title="Bot Status: All systems operational" if all_ok else "Bot Status: Issues detected",
            colour=colour,
            timestamp=datetime.now(timezone.utc),
        )
        for name, ok, detail in checks:
            emoji = "✅" if ok else "❌"
            embed.add_field(name=f"{emoji} {name}", value=detail or "OK", inline=False)
        return embed, all_ok

    @app_commands.command(name="bot_status", description="Run a health check and post the result to the status channel")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self._send_status_embed()
            ch = await self._resolve_status_channel()
            location = f"<#{BOT_STATUS_CHANNEL_ID}>" if ch else "status channel (unavailable)"
            await interaction.followup.send(f"Health report sent to {location}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Health report failed: {e!r}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HealthCog(bot))