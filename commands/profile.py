import discord
from discord.ext import commands
from discord import app_commands
import traceback

from database import get_linked_minecraft_name_async, supabase_select
from config import TICKET_TYPES, LEGACY_TICKET_TYPES, MODE_INDICATORS, normalize_gamemode

def get_formatted_emoji(mode_key: str, default_label: str) -> str:
    """
    Kikeresi a játékmódhoz tartozó emojit a MODE_INDICATORS-ból, 
    és átalakítja érvényes Discord emoji formátumra.
    """
    norm_key = normalize_gamemode(mode_key)
    raw_emoji = MODE_INDICATORS.get(norm_key, "")
    
    if not raw_emoji:
        return "⚔️"
    
    raw_emoji = str(raw_emoji).strip()
    
    # Ha már teljes emoji formátumban van (pl. <:vanilla:123456789>)
    if raw_emoji.startswith("<:") or raw_emoji.startswith("<a:"):
        return raw_emoji
    
    # Ha csak az ID van megadva (pl. 1489190924771381289)
    if raw_emoji.isdigit():
        clean_name = default_label.replace(" ", "").replace("-", "").lower()
        return f"<:{clean_name}:{raw_emoji}>"
        
    return raw_emoji

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

            # Lekérjük a játékos tesztjeit a Supabase-ből
            user_tests = await supabase_select("tests", {"username": mc_name})
            user_tiers = {}
            
            if user_tests:
                for row in user_tests:
                    gmode = str(row.get("gamemode", "")).strip().lower()
                    rnk = str(row.get("rank", "Unranked")).strip()
                    if rnk == "500":
                        rnk = "Unranked"
                    user_tiers[gmode] = rnk

            # ===============================
            # ELSŐ EMBED: MODERN JÁTÉKMÓDOK
            # ===============================
            embed_modern = discord.Embed(
                title=f"⚔️ {mc_name} Tier Profilja",
                color=discord.Color.blue()
            )
            embed_modern.set_thumbnail(url=f"https://minotar.net/helm/{mc_name}/256.png")
            embed_modern.add_field(name="───────────────", value="**🔥 MODERN MÓDOK**", inline=False)

            for label, key, _ in TICKET_TYPES:
                norm_key = normalize_gamemode(key)
                tier = user_tiers.get(label.lower(), user_tiers.get(norm_key, "Unranked"))
                
                emoji_str = get_formatted_emoji(key, label)
                embed_modern.add_field(name=f"{emoji_str} {label}", value=f"**{tier}**", inline=True)

            mod_rem = len(TICKET_TYPES) % 3
            if mod_rem != 0:
                for _ in range(3 - mod_rem):
                    embed_modern.add_field(name="\u200b", value="\u200b", inline=True)

            # ===============================
            # MÁSODIK EMBED: LEGACY JÁTÉKMÓDOK
            # ===============================
            embed_legacy = discord.Embed(color=discord.Color.gold())
            embed_legacy.add_field(name="───────────────", value="**🏛️ LEGACY MÓDOK**", inline=False)
            
            for label, key, _ in LEGACY_TICKET_TYPES:
                norm_key = normalize_gamemode(key)
                tier = user_tiers.get(label.lower(), user_tiers.get(norm_key, "Unranked"))
                
                emoji_str = get_formatted_emoji(key, label)
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
