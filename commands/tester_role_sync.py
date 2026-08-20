"""
NeonTiers Bot - Tester Role Sync (commands/tester_role_sync.py)

A Játékos kezelő oldalon (csak OWNER admin láthatja) minden játékmódhoz
tartozik egy "Tester" jelölőnégyzet a Supabase `tests` tábla
`is_tester` oszlopában. Ez a cog periodikusan (2 percenként) szinkronizálja
ez alapján a Discord TESTER_ROLE_ID rangot:

- Ha egy játékosnak BÁRMELYIK játékmódban be van pipálva a Tester jelölő,
  de nincs rajta a Discord rang -> ráteszi.
- Ha egy tagon rajta van a rang, de a Supabase-ben egyetlen sorában sincs
  bepipálva a Tester jelölő (pl. levették a weboldalon) -> leveszi a rangot.

A játékos -> Discord ID feloldás a `linked_accounts` táblán keresztül
történik (ugyanaz a minta, mint a ban_enforcement.py-ban).
"""

import logging

from discord.ext import commands, tasks

from config import TESTER_ROLE_ID, config
from database import get_tester_usernames_async, get_discord_by_minecraft_async

log = logging.getLogger("neontiers.commands.tester_role_sync")


class TesterRoleSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sync_testers.start()

    def cog_unload(self):
        self.sync_testers.cancel()

    @tasks.loop(minutes=2)
    async def sync_testers(self):
        guilds = [g for g in self.bot.guilds if not config.guild_id or g.id == config.guild_id]
        if not guilds:
            guilds = list(self.bot.guilds)
        if not guilds:
            return

        try:
            tester_usernames = await get_tester_usernames_async()
        except Exception as exc:
            log.error("Hiba a Tester játékosok lekérdezésekor: %s", exc)
            return

        should_have_role: set[int] = set()

        for username in tester_usernames:
            try:
                discord_id = await get_discord_by_minecraft_async(username)
            except Exception as exc:
                log.error("Hiba a Discord ID feloldásakor (%s) a linked_accounts alapján: %s", username, exc)
                continue
            if not discord_id:
                continue
            should_have_role.add(discord_id)
            await self._ensure_role(guilds, discord_id, reason="Tester jelölő bepipálva a weboldalon (Owner)")

        # Azok levétele, akiken rajta van a rang, de már egyetlen
        # játékmódban sincs bepipálva a Tester jelölő.
        for guild in guilds:
            role = guild.get_role(TESTER_ROLE_ID)
            if not role:
                continue
            for member in list(role.members):
                if member.id not in should_have_role:
                    try:
                        await member.remove_roles(role, reason="Nincs bepipált Tester jelölő a weboldalon")
                        log.info("Tester rang levéve %s (%s) tagról.", member, member.id)
                    except Exception as exc:
                        log.error("Hiba a Tester rang levételekor %s tagról: %s", member, exc)

    async def _ensure_role(self, guilds, discord_id: int, reason: str) -> None:
        for guild in guilds:
            role = guild.get_role(TESTER_ROLE_ID)
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
                    log.info("Tester rang rátéve %s (%s) tagra.", member, member.id)
                except Exception as exc:
                    log.error("Nem sikerült rátenni a Tester rangot %s tagra: %s", member, exc)

    @sync_testers.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TesterRoleSyncCog(bot))
