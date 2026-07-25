import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import time
import json
import os
from config import SUPABASE_URL, SUPABASE_KEY, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID

TESTER_ROLE_NAMES = ["Tester", "Regulator", "Manager", "Admin"]
COOLDOWN_FILE = "tier_cooldowns.json"
COOLDOWN_DAYS = 14

def load_cooldowns():
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cooldowns(data):
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[COOLDOWN SAVE ERROR] {e}")

GAMEMODES = [
    "Vanilla", "DiaSMP", "OGV", "NethPot", "Mace", "SMP", "Cart", 
    "SpearMace", "SpearElytra", "Trident", "Sword", "Uhc", "Pot", 
    "Creeper", "ShieldlessUHC", "Axe"
]

TIERS = [
    "HT1", "LT1", "HT2", "LT2", "HT3", "LT3", 
    "HT4", "LT4", "HT5", "LT5", "FT3", "FT4", "FT5", "FT6", "FT10", "FT20", "Retire"
]

class TierSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_tester_permissions(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        has_role = any(role.name in TESTER_ROLE_NAMES for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message("❌ Nincs jogosultságod a tesztek levezetéséhez és rangosztáshoz (szükséges rang: **Tester** vagy **Regulator**).", ephemeral=True)
            return False
        return True

    @app_commands.command(name="give-tier", description="Tier megadása egy játékosnak teszt után.")
    @app_commands.describe(
        discord_user="A játékos Discord felhasználója",
        minecraft_name="A játékos pontos Minecraft neve",
        gamemode="A játékmód, amiben a teszt történt",
        tier="Az elért tier / rang",
        is_public="Publikus kihirdetés legyen-e (igen/nem)"
    )
    @app_commands.choices(gamemode=[app_commands.Choice(name=mode, value=mode) for mode in GAMEMODES])
    @app_commands.choices(tier=[app_commands.Choice(name=t, value=t) for t in TIERS])
    @app_commands.choices(is_public=[
        app_commands.Choice(name="Igen (Kihirdetés a csatornán)", value="yes"),
        app_commands.Choice(name="Nem (Csak adatbázis mentés)", value="no")
    ])
    async def give_tier(
        self, 
        interaction: discord.Interaction, 
        discord_user: discord.Member, 
        minecraft_name: str, 
        gamemode: str, 
        tier: str, 
        is_public: str
    ):
        if not await self.check_tester_permissions(interaction):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        uid = str(discord_user.id)
        gmode = gamemode.lower()
        now = time.time()

        # Cooldown ellenőrzés (14 nap)
        cd_data = load_cooldowns()
        if uid in cd_data and gmode in cd_data[uid]:
            expires_at = cd_data[uid][gmode]
            if now < expires_at:
                remaining_days = math.ceil((expires_at - now) / (24 * 60 * 60))
                await interaction.followup.send(
                    f"❌ Ennek a játékosnak még aktív cooldown-ja van a(z) `{gamemode}` játékmódban!\n"
                    f"Még **{remaining_days} nap** van hátra az újratesztelésig.",
                    ephemeral=True
                )
                return

        # Supabase mentés
        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba: Hiányzó Supabase konfiguráció.", ephemeral=True)
            return

        headers = {
            "apikey": SUPABASE_KEY, 
            "Authorization": f"Bearer {SUPABASE_KEY}", 
            "Content-Type": "application/json", 
            "Prefer": "return=minimal"
        }
        unique_id = int(now * 1000)
        payload = {
            "id": unique_id,
            "username": minecraft_name.strip(),
            "gamemode": gmode,
            "rank": tier,
            "tester_id": str(interaction.user.id),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests"
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status not in [200, 201]:
                        err = await resp.text()
                        await interaction.followup.send(f"❌ Nem sikerült menteni az adatbázisba: {err}", ephemeral=True)
                        return
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt a mentés során: {str(e)}", ephemeral=True)
            return

        # Cooldown beállítása a következő 14 napra
        if uid not in cd_data:
            cd_data[uid] = {}
        cd_data[uid][gmode] = now + (COOLDOWN_DAYS * 24 * 60 * 60)
        save_cooldowns(cd_data)

        # Sikeres válasz a teszternek
        await interaction.followup.send(
            f"✅ A tier sikeresen rögzítve!\n"
            f"• **Játékos:** `{minecraft_name}` ({discord_user.mention})\n"
            f"• **Játékmód:** `{gamemode}`\n"
            f"• **Elért Tier:** `**{tier}**`\n"
            f"• **Cooldown:** Beállítva 14 napra.",
            ephemeral=True
        )

        # Nyilvános eredmény kihirdetés (ha az "igen"-t választotta)
        if is_public == "yes":
            if MODERN_RESULT_CHANNEL_ID:
                try:
                    channel = self.bot.get_channel(MODERN_RESULT_CHANNEL_ID) or await self.bot.fetch_channel(MODERN_RESULT_CHANNEL_ID)
                    if channel:
                        embed = discord.Embed(
                            title="🏆 Új Tier Teszt Eredmény", 
                            color=discord.Color.blue(), 
                            timestamp=datetime.datetime.now(datetime.timezone.utc)
                        )
                        embed.add_field(name="Játékos", value=f"`{minecraft_name}` ({discord_user.mention})", inline=True)
                        embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                        embed.add_field(name="Elért Rank", value=f"**{tier}**", inline=True)
                        embed.add_field(name="Teszter", value=interaction.user.mention, inline=False)
                        embed.set_footer(text="NeoTiers Official Tiers")
                        await channel.send(embed=embed)
                except Exception as e:
                    print(f"[MODERN RESULT ERROR] {e}")

            if LEGACY_RESULT_CHANNEL_ID:
                try:
                    channel = self.bot.get_channel(LEGACY_RESULT_CHANNEL_ID) or await self.bot.fetch_channel(LEGACY_RESULT_CHANNEL_ID)
                    if channel:
                        embed = discord.Embed(
                            title="🏆 Új Tier Teszt Eredmény (Legacy)", 
                            color=discord.Color.dark_blue(), 
                            timestamp=datetime.datetime.now(datetime.timezone.utc)
                        )
                        embed.add_field(name="Játékos", value=f"`{minecraft_name}` ({discord_user.mention})", inline=True)
                        embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                        embed.add_field(name="Elért Rank", value=f"**{tier}**", inline=True)
                        embed.add_field(name="Teszter", value=interaction.user.mention, inline=False)
                        embed.set_footer(text="NeoTiers Legacy Tiers")
                        await channel.send(embed=embed)
                except Exception as e:
                    print(f"[LEGACY RESULT ERROR] {e}")

async def setup(bot):
    import math
    await bot.add_cog(TierSystemCog(bot))
