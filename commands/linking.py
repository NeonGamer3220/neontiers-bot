import discord
from discord.ext import commands
from discord import app_commands
from database import (
    get_linked_minecraft_name_async, 
    generate_link_code_async,
    unlink_minecraft_account_async
)

class LinkingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="link", description="Kérj egy kódot a Minecraft fiókod összekapcsolásához!")
    async def link(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Ellenőrizzük, hogy már össze van-e linkelve
        existing = await get_linked_minecraft_name_async(interaction.user.id)
        if existing:
            await interaction.followup.send(f"❌ Te már össze vagy linkelve ezzel a fiókkal: **{existing}**\nHasználd az `/unlink` parancsot a leválasztáshoz!", ephemeral=True)
            return
            
        # Kód generálása és adatbázisba mentése
        code = await generate_link_code_async(interaction.user.id)
        
        if not code:
            await interaction.followup.send("❌ Hiba történt a kód generálásakor az adatbázisban!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🔗 Fiók Összekapcsolása",
            description=(
                f"✅ A kódod sikeresen legenerálva!\n\n"
                f"Lépj fel a Minecraft szerverre, és írd be ezt a parancsot:\n"
                f"**`/link {code}`**\n\n"
                f"⏱️ *A kód 10 perc múlva lejár!*\n"
                f"🌐 **Szerver IP:** `chaosffa.kinetic.host`"
            ),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="unlink", description="Minecraft fiókod leválasztása")
    async def unlink(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success = await unlink_minecraft_account_async(interaction.user.id)
        if success:
            await interaction.followup.send("✅ Sikeresen leválasztottad a Minecraft fiókodat!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Nem voltál összelinkelve egyetlen Minecraft fiókkal sem.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LinkingCog(bot))