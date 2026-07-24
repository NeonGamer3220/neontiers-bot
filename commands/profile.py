"""
NeonTiers Bot - Profile Parancs (commands/profile.py)
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    get_gamemode_display_name,
    get_gamemode_indicator,
    normalize_gamemode,
)
from database import (
    arun,
    get_linked_minecraft_name_async,
    supabase_select,
)

log = logging.getLogger("neontiers.commands.profile")


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

        # 2. Tesztek lekérése Minecraft név és Discord ID alapján is
        try:
            user_tests = await arun(supabase_select, "tests", "username", mc_name)
            if not user_tests:
                user_tests = await arun(supabase_select, "tests", "discord_id", str(discord_id))
        except Exception as exc:
            log.error("Hiba a profil tesztjeinek lekérésekor: %s", exc)
            user_tests = []

        # 3. Embed összeállítása
        embed = discord.Embed(
            title=f"🎮 {mc_name} Profilja",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=f"https://mc-heads.net/avatar/{mc_name}/100")
        embed.add_field(name="Discord azonosító", value=target_user.mention, inline=True)
        embed.add_field(name="Minecraft név", value=f"`{mc_name}`", inline=True)

        if user_tests:
            formatted_results = []
            for test in user_tests:
                mode = test.get("gamemode") or test.get("mode") or test.get("game_mode", "Ismeretlen")
                rank = test.get("rank") or test.get("tier", "Unranked")
                
                norm_mode = normalize_gamemode(mode)
                display_name = get_gamemode_display_name(norm_mode)
                indicator = get_gamemode_indicator(norm_mode)

                formatted_results.append(f"{indicator} **{display_name}:** `{rank}`")

            results_text = "\n".join(formatted_results)
            if len(results_text) > 1024:
                results_text = results_text[:1020] + "..."

            embed.add_field(
                name="📊 Tier Teszt Eredmények",
                value=results_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📊 Tier Teszt Eredmények",
                value="*Még nincsenek rögzített eredmények.*",
                inline=False
            )

        embed.set_footer(text=f"NeonTiers.hu • Lekérve: {interaction.created_at.strftime('%Y-%m-%d %H:%M')}")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
