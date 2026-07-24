"""
NeonTiers Bot - Profile Parancs (commands/profile.py)
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    LEGACY_TICKET_TYPES,
    get_gamemode_display_name,
    get_gamemode_indicator,
    normalize_gamemode,
)
from database import (
    arun,
    db,
    get_linked_minecraft_name_async,
)

log = logging.getLogger("neontiers.commands.profile")

# Legacy játékmódok kulcsai a szétválasztáshoz
LEGACY_KEYS = {key.lower() for _, key, _ in LEGACY_TICKET_TYPES}


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="profile", description="Megtekintheted a saját vagy egy másik játékos profilját.")
    @app_commands.describe(user="A játékos, akinek a profilját meg szeretnéd nézni (opcionális).")
    async def profile(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        await interaction.response.defer()

        target_user = user or interaction.user
        discord_id = target_user.id

        # 1. Minecraft név lekérése
        mc_name = await get_linked_minecraft_name_async(discord_id)

        if not mc_name:
            if user:
                await interaction.followup.send(
                    f"❌ **{target_user.display_name}** nem kapcsolta össze a Discord fiókját egyetlen Minecraft fiókkal sem."
                )
            else:
                await interaction.followup.send(
                    "❌ Még nem kapcsoltad össze a Discord fiókodat! Használd a `/link` parancsot."
                )
            return

        # 2. Tesztek lekérése közvetlenül a `tests` táblából (kis-/nagybetű függetlenül)
        user_tests = []
        if db._client:
            try:
                def fetch_tests():
                    resp = db._client.table("tests").select("*").ilike("username", mc_name).execute()
                    return resp.data or []

                user_tests = await arun(fetch_tests)
            except Exception as exc:
                log.error("Hiba a 'tests' tábla lekérésekor: %s", exc)

        # 3. Embed összeállítása
        embed = discord.Embed(
            title=f"🎮 {mc_name} Profilja",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=f"https://mc-heads.net/avatar/{mc_name}/100")
        embed.add_field(name="Discord azonosító", value=target_user.mention, inline=True)
        embed.add_field(name="Minecraft név", value=f"`{mc_name}`", inline=True)

        modern_results = []
        legacy_results = []

        if user_tests:
            for test in user_tests:
                # Elvonatkoztatott/visszavont tesztek kiszűrése
                if test.get("retired"):
                    continue

                mode = test.get("gamemode", "Ismeretlen")
                rank = test.get("rank", "Unranked")
                
                norm_mode = normalize_gamemode(mode)
                display_name = get_gamemode_display_name(norm_mode)
                indicator = get_gamemode_indicator(norm_mode)

                # Formázott sor az ikonnal és megnevezéssel
                entry = f"{indicator} **{display_name}:** `{rank}`"

                # Különválasztás: Legacy vagy Modern játékmód
                if norm_mode in LEGACY_KEYS:
                    legacy_results.append(entry)
                else:
                    modern_results.append(entry)

        # Modern eredmények megjelenítése (új sorokkal elválasztva)
        if modern_results:
            embed.add_field(
                name="📊 Modern Tier Eredmények",
                value="\n".join(modern_results)[:1024],
                inline=False
            )
        else:
            embed.add_field(
                name="📊 Modern Tier Eredmények",
                value="*Nincsenek rögzített modern eredmények.*",
                inline=False
            )

        # Legacy eredmények megjelenítése (ha vannak)
        if legacy_results:
            embed.add_field(
                name="📜 Legacy Tier Eredmények",
                value="\n".join(legacy_results)[:1024],
                inline=False
            )

        embed.set_footer(text=f"NeonTiers.hu • Lekérve: {interaction.created_at.strftime('%Y-%m-%d %H:%M')}")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
