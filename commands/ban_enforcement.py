"""
NeonTiers Bot - Ban Enforcement (commands/ban_enforcement.py)

A kitiltásokat a weboldali admin panel kezeli, ami a Supabase `bans`
táblájába ír (username, discord_id, reason, duration_key, expires_at,
active, banned_by, image_url, created_at).

Ez a cog periodikusan (5 percenként) lekérdezi a Supabase-ből az aktív
(active=true) kitiltásokat, és ez alapján szinkronizálja a Discord
kitiltási rangot (BANNED_ROLE_ID):

- Ha egy játékosnak aktív, még nem lejárt bannja van a táblában, de nincs
  rajta a rang -> ráteszi.
- Ha egy bann lejárt (expires_at < most) -> leveszi a rangot, és a
  Supabase-ben inaktívra (`active = false`) állítja a sort.
- Ha egy tagon rajta van a rang, de a Supabase-ben nincs hozzá tartozó
  aktív bann (pl. a weboldalon feloldották) -> leveszi a rangot.

A `discord_id` mező lehet üres a táblában (pl. ha csak Minecraft
felhasználónév alapján lett kitiltva); ebben az esetben a bot a
`linked_accounts` táblából próbálja megkeresni a hozzá tartozó Discord
ID-t.
"""

import logging
import time

import discord
from discord.ext import commands, tasks

from config import BANNED_ROLE_ID, config
from database import get_active_bans_async, deactivate_ban_async, get_discord_by_minecraft_async

log = logging.getLogger("neontiers.commands.ban_enforcement")


def _parse_expires_at(value) -> float | None:
    """A Supabase 'timestamp with time zone' mezőt Unix timestamp-re alakítja."""
    if not value:
        return None
    try:
        from datetime import datetime
        # Supabase ISO formátumban adja vissza, pl. "2026-08-20T12:00:00+00:00"
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def is_banned_by_role(member: discord.Member) -> bool:
    if not member or not hasattr(member, "roles"):
        return False
    return any(r.id == BANNED_ROLE_ID for r in member.roles)


class BanEnforcementCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sync_bans.start()

    def cog_unload(self):
        self.sync_bans.cancel()

    async def _resolve_discord_id(self, ban_row: dict) -> int | None:
        raw_id = ban_row.get("discord_id")
        if raw_id:
            try:
                return int(raw_id)
            except (TypeError, ValueError):
                pass

        username = ban_row.get("username")
        if username:
            try:
                return await get_discord_by_minecraft_async(username)
            except Exception as exc:
                log.error("Hiba a Discord ID feloldásakor (%s) a linked_accounts alapján: %s", username, exc)
        return None

    @tasks.loop(minutes=5)
    async def sync_bans(self):
        guilds = [g for g in self.bot.guilds if not config.guild_id or g.id == config.guild_id]
        if not guilds:
            guilds = list(self.bot.guilds)
        if not guilds:
            return

        try:
            active_bans = await get_active_bans_async()
        except Exception as exc:
            log.error("Hiba az aktív bannok lekérdezésekor: %s", exc)
            return

        now = time.time()
        should_be_banned: set[int] = set()

        for ban_row in active_bans:
            expires_at = _parse_expires_at(ban_row.get("expires_at"))

            discord_id = await self._resolve_discord_id(ban_row)

            # Lejárt bann -> inaktiválás Supabase-ben, rang levétele
            if expires_at is not None and now >= expires_at:
                ban_id = ban_row.get("id")
                if ban_id is not None:
                    await deactivate_ban_async(ban_id)
                if discord_id:
                    await self._remove_role_everywhere(guilds, discord_id, reason="Kitiltás lejárt (Supabase)")
                continue

            if discord_id:
                should_be_banned.add(discord_id)
                await self._ensure_role(guilds, discord_id, ban_row, reason="Weboldali kitiltás szinkronizálása (Supabase)")

        # Azok levétele, akiknek van rangja, de már nincs hozzá aktív bann sor
        for guild in guilds:
            role = guild.get_role(BANNED_ROLE_ID)
            if not role:
                continue
            for member in list(role.members):
                if member.id not in should_be_banned:
                    try:
                        await member.remove_roles(role, reason="Nincs aktív bann a Supabase-ben (feloldva a weboldalon)")
                        log.info("Kitiltási rang levéve %s (%s) tagról, mivel nincs hozzá aktív bann.", member, member.id)
                    except Exception as exc:
                        log.error("Hiba a rang levételekor %s tagról: %s", member, exc)

    async def _ensure_role(self, guilds, discord_id: int, ban_row: dict, reason: str) -> None:
        for guild in guilds:
            role = guild.get_role(BANNED_ROLE_ID)
            if not role:
                continue
            member = guild.get_member(discord_id)
            if not member:
                try:
                    member = await guild.fetch_member(discord_id)
                except Exception:
                    continue
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=reason)
                    log.info("Kitiltási rang rátéve %s (%s) tagra (%s).", member, member.id, ban_row.get("reason", ""))
                except Exception as exc:
                    log.error("Nem sikerült rátenni a kitiltási rangot %s tagra: %s", member, exc)

    async def _remove_role_everywhere(self, guilds, discord_id: int, reason: str) -> None:
        for guild in guilds:
            role = guild.get_role(BANNED_ROLE_ID)
            if not role:
                continue
            member = guild.get_member(discord_id)
            if not member:
                try:
                    member = await guild.fetch_member(discord_id)
                except Exception:
                    continue
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=reason)
                    log.info("Kitiltási rang levéve %s (%s) tagról (%s).", member, member.id, reason)
                except Exception as exc:
                    log.error("Nem sikerült levenni a kitiltási rangot %s tagról: %s", member, exc)

    @sync_bans.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BanEnforcementCog(bot))
