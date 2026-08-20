"""
NeonTiers Bot - Tester Role Sync (commands/tester_role_sync.py)

A Játékos kezelő oldalon (csak OWNER admin láthatja) minden játékmódhoz
tartozik egy "Tester" jelölőnégyzet a Supabase `tests` tábla
`is_tester` oszlopában (soronként, játékmódonként). Ez a cog periodikusan
(2 percenként) szinkronizálja ez alapján a Discord rangokat:

- Általános TESTER_ROLE_ID rang: ha egy játékosnak BÁRMELYIK játékmódban
  be van pipálva a Tester jelölő, megkapja; ha egyikben sincs, leveszi.
- Játékmódonkénti "{Játékmód} Tester" rang (pl. "DiaSMP Tester"): csak azt
  a rangot kapja meg, amelyik játékmódhoz ténylegesen be van pipálva a
  Tester jelölő. Így ha valakinek megvan az általános Tester rangja, de
  nincs Diasmp Testere, a queue-megnyitási jogosultság-ellenőrzés
  (lásd commands/tier_ui.py) nem engedi neki megnyitni a DiaSMP várólistát.

A játékos -> Discord ID feloldás a `linked_accounts` táblán keresztül
történik (ugyanaz a minta, mint a ban_enforcement.py-ban).
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import TESTER_ROLE_ID, ALL_TICKET_TYPES, config
from database import (
    get_tester_usernames_async,
    get_tester_gamemode_rows_async,
    get_discord_by_minecraft_async,
)

log = logging.getLogger("neontiers.commands.tester_role_sync")

# Az összes ismert játékmód-címke (pl. "DiaSMP"), amihez "{label} Tester"
# nevű Discord rang tartozhat a szerveren.
_ALL_GAMEMODE_LABELS = [label for label, _key, _emoji in ALL_TICKET_TYPES]


class TesterRoleSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sync_testers.start()

    def cog_unload(self):
        self.sync_testers.cancel()

    @tasks.loop(seconds=30)
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

        try:
            gamemode_rows = await get_tester_gamemode_rows_async()
        except Exception as exc:
            log.error("Hiba a játékmódonkénti Tester sorok lekérdezésekor: %s", exc)
            gamemode_rows = []

        discord_id_cache: dict[str, int | None] = {}

        async def resolve(username: str) -> int | None:
            if username in discord_id_cache:
                return discord_id_cache[username]
            try:
                discord_id = await get_discord_by_minecraft_async(username)
            except Exception as exc:
                log.error("Hiba a Discord ID feloldásakor (%s) a linked_accounts alapján: %s", username, exc)
                discord_id = None
            discord_id_cache[username] = discord_id
            return discord_id

        # --- Kik kapják meg az általános Tester rangot ---
        should_have_role: set[int] = set()
        for username in tester_usernames:
            discord_id = await resolve(username)
            if discord_id:
                should_have_role.add(discord_id)

        # --- discord_id -> {játékmód címkék, amikhez Tester jelölő van} ---
        should_have_gamemode_roles: dict[int, set[str]] = {}
        for row in gamemode_rows:
            username = row["username"]
            gamemode_label = row["gamemode"]
            discord_id = await resolve(username)
            if not discord_id:
                continue
            should_have_gamemode_roles.setdefault(discord_id, set()).add(gamemode_label)

        for guild in guilds:
            general_role = guild.get_role(TESTER_ROLE_ID)

            # --- Általános Tester rang kiosztása / levétele ---
            if general_role:
                for discord_id in should_have_role:
                    await self._ensure_role(guild, general_role, discord_id, reason="Tester jelölő bepipálva a weboldalon (Owner)")

                for member in list(general_role.members):
                    if member.id not in should_have_role:
                        try:
                            await member.remove_roles(general_role, reason="Nincs bepipált Tester jelölő a weboldalon")
                            log.info("Tester rang levéve %s (%s) tagról.", member, member.id)
                        except Exception as exc:
                            log.error("Hiba a Tester rang levételekor %s tagról: %s", member, exc)

            # --- Játékmódonkénti "{label} Tester" / "{label} Teszter" rangok kiosztása / levétele ---
            for label in _ALL_GAMEMODE_LABELS:
                gm_role = None
                for suffix in ("Tester", "Teszter"):
                    gm_role = discord.utils.get(guild.roles, name=f"{label} {suffix}")
                    if gm_role:
                        break
                if not gm_role:
                    continue

                should_have_this: set[int] = {
                    discord_id
                    for discord_id, labels in should_have_gamemode_roles.items()
                    if label in labels
                }

                for discord_id in should_have_this:
                    await self._ensure_role(guild, gm_role, discord_id, reason=f"{label} Tester jelölő bepipálva a weboldalon (Owner)")

                for member in list(gm_role.members):
                    if member.id not in should_have_this:
                        try:
                            await member.remove_roles(gm_role, reason=f"Nincs bepipált {label} Tester jelölő a weboldalon")
                            log.info("%s Tester rang levéve %s (%s) tagról.", label, member, member.id)
                        except Exception as exc:
                            log.error("Hiba a(z) %s Tester rang levételekor %s tagról: %s", label, member, exc)

    async def _ensure_role(self, guild, role, discord_id: int, reason: str) -> None:
        member = guild.get_member(discord_id)
        if not member:
            try:
                member = await guild.fetch_member(discord_id)
            except Exception:
                return
        if role not in member.roles:
            try:
                await member.add_roles(role, reason=reason)
                log.info("%s rang rátéve %s (%s) tagra.", role.name, member, member.id)
            except Exception as exc:
                log.error("Nem sikerült rátenni a(z) %s rangot %s tagra: %s", role.name, member, exc)

    @sync_testers.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="synctesters", description="Azonnal újraszinkronizálja a Tester rangokat (Admin).")
    async def synctesters(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Ehhez a parancshoz admin jogosultság szükséges.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await self.sync_testers()
        except Exception as exc:
            log.error("Hiba a manuális Tester szinkronizáláskor: %s", exc)
            return await interaction.followup.send(f"❌ Hiba történt a szinkronizálás közben: {exc}", ephemeral=True)
        await interaction.followup.send("✅ Tester rangok szinkronizálva.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TesterRoleSyncCog(bot))
