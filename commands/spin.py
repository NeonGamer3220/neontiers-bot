import discord
from discord.ext import commands
from discord import app_commands
import random

from database import db, get_discord_by_minecraft_async
from config import get_gamemode_display_name, normalize_gamemode

class SpinCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="spin", description="Kisorsol egy véletlenszerű játékost az adatbázisból tesztelésre.")
    @app_commands.describe(
        gamemode="Melyik játékmódból sorsoljon? (pl. sword, mace)",
        tier="Melyik tierből sorsoljon? (pl. Unranked, LT5, HT3)"
    )
    async def spin(self, interaction: discord.Interaction, gamemode: str, tier: str):
        await interaction.response.defer()
        
        mode_display = get_gamemode_display_name(gamemode)
        target_tier = tier.strip().upper()
        
        if target_tier in ["UNRANKED", "500"]:
            target_tier = "UNRANKED"

        if not db._client:
            await interaction.followup.send("❌ Adatbázis kapcsolat nem elérhető.")
            return

        try:
            resp = db._client.table("tests").select("*").ilike("gamemode", mode_display).execute()
            mode_players = resp.data if resp.data else []
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba az adatbázis lekérdezésekor: `{e}`")
            return
        
        valid_targets = []
        for p in mode_players:
            rank = str(p.get("rank", "Unranked")).strip().upper()
            if rank == "500":
                rank = "UNRANKED"
            if rank == target_tier:
                valid_targets.append(p)
                
        if not valid_targets:
            await interaction.followup.send(f"❌ Nem található egyetlen játékos sem ebben a játékmódban (`{mode_display}`) ezen a szinten (`{tier}`).")
            return

        winner = random.choice(valid_targets)
        winner_mc = winner.get("username", "Ismeretlen")
        winner_rank = str(winner.get("rank", "Unranked"))
        
        if winner_rank in ["500", "UNRANKED", "unranked"]:
            winner_rank = "Unranked"
        else:
            winner_rank = winner_rank.upper()
            
        discord_id = await get_discord_by_minecraft_async(winner_mc)
        discord_mention = f"<@{discord_id}>" if discord_id else "*Nincs linkelve a szerveren*"
        
        embed = discord.Embed(
            title="🎯 **Pörgetés eredménye**", 
            description="A sorsolás nyertese:", 
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=f"https://minotar.net/helm/{winner_mc}/256.png")
        embed.add_field(name="Discord", value=discord_mention, inline=False)
        embed.add_field(name="Minecraft név", value=f"`{winner_mc}`", inline=False)
        embed.add_field(name="Játékmód", value=mode_display, inline=True)
        embed.add_field(name="Szint (Tier)", value=f"**{winner_rank}**", inline=True)
        embed.set_footer(text="NeoTiers Spin System")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SpinCog(bot))
