import discord
from discord.ext import commands
from discord import app_commands
import random

from database import supabase_select, get_discord_by_minecraft_async
from config import get_gamemode_display_name

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
        
        # Lekérjük az összes játékost a megadott játékmódból
        all_players = await supabase_select("tests", {"gamemode": mode_display})
        
        target_tier = tier.strip().upper()
        if target_tier == "UNRANKED" or target_tier == "500":
            target_tier = "UNRANKED"

        # Rászűrünk pontosan a megadott Tier-re
        valid_targets = []
        for p in all_players:
            rank = str(p.get("rank", "Unranked")).strip().upper()
            if rank == "500": 
                rank = "UNRANKED"
                
            if rank == target_tier:
                valid_targets.append(p)
        
        if not valid_targets:
            return await interaction.followup.send(f"❌ Nincs sorsolható játékos ebben a módban (`{mode_display}`) ezen a szinten (`{tier}`).")

        winner = random.choice(valid_targets)
        winner_mc = winner.get("username", "Ismeretlen")
        winner_rank = str(winner.get("rank", "Unranked"))
        if winner_rank == "500": 
            winner_rank = "Unranked"
            
        # Formázzuk szép kisbetű-nagybetűsre, ha Unranked
        if winner_rank.upper() == "UNRANKED":
            winner_rank = "Unranked"
        else:
            winner_rank = winner_rank.upper()
            
        # Visszakeressük a Discord fiókját a Minecraft neve alapján
        discord_id = await get_discord_by_minecraft_async(winner_mc)
        discord_mention = f"<@{discord_id}>" if discord_id else "*Nincs linkelve a szerveren*"
        
        embed = discord.Embed(title="**Pörgetés eredménye**", description="A sorsolás eredménye:", color=discord.Color.orange())
        
        # Minecraft fej betöltése
        embed.set_thumbnail(url=f"https://minotar.net/helm/{winner_mc}/256.png")
        
        embed.add_field(name="Discord", value=discord_mention, inline=False)
        embed.add_field(name="Minecraft név", value=f"`{winner_mc}`", inline=False)
        embed.add_field(name="Játékmód", value=mode_display, inline=True)
        embed.add_field(name="Tier", value=winner_rank, inline=True)
        embed.set_footer(text=f"Kérte: {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SpinCog(bot))