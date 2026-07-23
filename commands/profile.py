import discord
from discord.ext import commands
from discord import app_commands
import traceback

from database import get_linked_minecraft_name_async, supabase_select
from config import TICKET_TYPES, LEGACY_TICKET_TYPES, GAMEMODE_INDICATORS, normalize_gamemode


def get_emoji_from_config(mode_key: str, fallback_emoji: str) -> str:
    """
    Szigorúan kisbetűsített és tisztított kulcs alapján keresi meg az emojit a GAMEMODE_INDICATORS-ban.
    """
    # Tisztítjuk a kulcsot: pl. "Spear Elytra" -> "spearelytra"
    clean_key = mode_key.lower().replace(" ", "").replace("-", "").strip()
    norm_key = normalize_gamemode(clean_key)

    # 1. Próba a tisztított kulccsal
    if norm_key in GAMEMODE_INDICATORS:
        return GAMEMODE_INDICATORS[norm_key]
    
    # 2. Próba a szimpla tisztított kulccsal
    if clean_key in GAMEMODE_INDICATORS:
        return GAMEMODE_INDICATORS[clean_key]

    # 3. Ha semmi nem nyert, visszaadja a TICKET_TYPES-ból a 3. elemet
    return fallback_emoji or "⚔️"


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Nézd meg a saját, vagy más játékos Tier profilját!")
    @app_commands.describe(user="A játékos, akinek a profilját látni szeretnéd (opcionális)")
    async def profile(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(ephemeral=False)
        
        try:
            target_user = user or interaction.user
            mc_name = await get_linked_minecraft_name_async(target_user.id)
            
            if not mc_name:
                if user:
                    await interaction.followup.send(f"❌ **{target_user.display_name}** még nem linkelte a Minecraft fiókját!")
                else:
                    await interaction.followup.send("❌ Még nem linkelted a Minecraft fiókodat! Használd a `/link` parancsot.")
                return

            user_tests = await supabase_select("tests", {"username": mc_name})
            user_tiers = {}
            
            if user_tests:
                for row in user_tests:
                    gmode = str(row.get("gamemode", "")).lower().replace(" ", "").replace("-", "").strip()
                    rnk = str(row.get("rank", "Unranked")).strip()
                    if rnk == "500":
                        rnk = "Unranked"
                    user_tiers[gmode] = rnk

            # ===============================
            # MODERN MÓDOK EMBED
            # ===============================
            embed_modern = discord.Embed(
                title=f"⚔️ {mc_name} Tier Profilja",
                color=discord.Color.blue()
            )
            embed_modern.set_thumbnail(url=f"https://minotar.net/helm/{mc_name}/256.png")
            embed_modern.add_field(name="───────────────", value="**🔥 MODERN MÓDOK**", inline=False)

            for label, key, raw_emoji in TICKET_TYPES:
                clean_key = key.lower().replace(" ", "").replace("-", "").strip()
                tier = user_tiers.get(clean_key, user_tiers.get(label.lower(), "Unranked"))
                
                emoji_str = get_emoji_from_config(key, raw_emoji)
                embed_modern.add_field(name=f"{emoji_str} {label}", value=f"**{tier}**", inline=True)

            mod_rem = len(TICKET_TYPES) % 3
            if mod_rem != 0:
                for _ in range(3 - mod_rem):
                    embed_modern.add_field(name="\u200b", value="\u200b", inline=True)

            # ===============================
            # LEGACY MÓDOK EMBED
            # ===============================
            embed_legacy = discord.Embed(color=discord.Color.gold())
            embed_legacy.add_field(name="───────────────", value="**🏛️ LEGACY MÓDOK**", inline=False)
            
            for label, key, raw_emoji in LEGACY_TICKET_TYPES:
                clean_key = key.lower().replace(" ", "").replace("-", "").strip()
                tier = user_tiers.get(clean_key, user_tiers.get(label.lower(), "Unranked"))
                
                emoji_str = get_emoji_from_config(key, raw_emoji)
                embed_legacy.add_field(name=f"{emoji_str} {label}", value=f"**{tier}**", inline=True)

            leg_rem = len(LEGACY_TICKET_TYPES) % 3
            if leg_rem != 0:
                for _ in range(3 - leg_rem):
                    embed_legacy.add_field(name="\u200b", value="\u200b", inline=True)

            await interaction.followup.send(embeds=[embed_modern, embed_legacy])
            
        except Exception as e:
            print(f"[PROFILE ERROR] {traceback.format_exc()}")
            await interaction.followup.send("❌ Hiba történt a profil lekérdezése közben.")

async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
