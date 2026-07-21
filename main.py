import os
import sys
import asyncio
import discord
from discord.ext import commands
import aiohttp

from config import DISCORD_TOKEN, GUILD_ID
from database import init_db, close_db

class NeonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)
        self.http_session = None

    # A setup_hook garantáltan csak egyszer fut le a bot elindulása előtt!
    async def setup_hook(self):
        print("Parancsok betöltése a commands mappából...")
        for filename in os.listdir("./commands"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"commands.{filename[:-3]}")
                    print(f"✅ Betöltve: {filename}")
                except Exception as e:
                    print(f"❌ Hiba {filename}: {e}")

        try:
            # Perzisztens gombok regisztrálása (Matchmaking törölve, csak a TGF marad)
            from commands.tgf import TGFPanelView
            self.add_view(TGFPanelView())
            print("🎯 SIKER: TGF gombok regisztrálva!")
        except Exception as e:
            print(f"❌ Nem sikerült a gombokat regisztrálni: {e}")

        try:
            # Slash parancsok szinkronizálása
            if GUILD_ID:
                g = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=g)
                await self.tree.sync(guild=g)
                print("🚀 Slash parancsok szinkronizálva!")
            else:
                await self.tree.sync()
                print("🚀 Slash parancsok globálisan szinkronizálva!")
        except Exception as e:
            print(f"Sync hiba: {e}")

bot = NeonBot()

@bot.event
async def on_ready():
    print(f"Bejelentkezve: {bot.user}")

# ==========================================
# ÜDVÖZLŐ ÜZENET (WELCOME SYSTEM)
# ==========================================
@bot.event
async def on_member_join(member: discord.Member):
    channel = member.guild.get_channel(1505942483098533908)
    
    if channel:
        join_date = member.joined_at.strftime("%Y. %m. %d.") if member.joined_at else "Ismeretlen"
        
        embed = discord.Embed(
            title="⚔️ Új harcos érkezett a NeonTiers.hu-ra!",
            description=(
                f"Üdv a szerveren, {member.mention}!\n\n"
                f"Örülünk, hogy itt vagy. Nézz körül, készülj a párbajokra, "
                f"és érezd jól magad a NeonTiers.hu közösségben."
            ),
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            
        embed.set_footer(text=f"Felhasználó ID: {member.id} - {join_date}")
        
        await channel.send(content=member.mention, embed=embed)

async def main():
    await init_db()
    
    async with aiohttp.ClientSession() as session:
        bot.http_session = session
        try:
            await bot.start(DISCORD_TOKEN)
        except Exception as e:
            print(f"❌ Hiba a bot futása közben: {e}")
        finally:
            if not bot.is_closed():
                await bot.close()
            await close_db()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot kézzel leállítva.")