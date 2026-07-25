import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import time
from config import SUPABASE_URL, SUPABASE_KEY, LOG_CHANNEL_ID, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID

REGULATOR_ROLE_NAME = "Regulator"

async def send_test_announcements(bot: discord.Client, username: str, gamemode: str, rank: str, tester: discord.User):
    if MODERN_RESULT_CHANNEL_ID:
        try:
            channel = bot.get_channel(MODERN_RESULT_CHANNEL_ID) or await bot.fetch_channel(MODERN_RESULT_CHANNEL_ID)
            if channel:
                embed = discord.Embed(title="🏆 Új Tier Teszt Eredmény", color=discord.Color.blue(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.add_field(name="Játékos", value=f"`{username}`", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{rank}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Official Tiers")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[MODERN RESULT ERROR] {e}")

    if LEGACY_RESULT_CHANNEL_ID:
        try:
            channel = bot.get_channel(LEGACY_RESULT_CHANNEL_ID) or await bot.fetch_channel(LEGACY_RESULT_CHANNEL_ID)
            if channel:
                embed = discord.Embed(title="🏆 Új Tier Teszt Eredmény (Legacy)", color=discord.Color.dark_blue(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.add_field(name="Játékos", value=f"`{username}`", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{rank}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Legacy Tiers")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[LEGACY RESULT ERROR] {e}")

async def send_log(bot: discord.Client, title: str, description: str, color: discord.Color, fields: list = None):
    if not LOG_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID) or await bot.fetch_channel(LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
            if fields:
                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)
            embed.set_footer(text="NeoTiers Audit Log")
            await channel.send(embed=embed)
    except Exception as e:
        print(f"[LOG ERROR] {e}")

class ManualTestModal(discord.ui.Modal, title="Manuális Teszt Rögzítés (LT3-ig)"):
    minecraft_name = discord.ui.TextInput(label="Játékos Minecraft neve", placeholder="pl. Steve123", required=True, max_length=50)
    gamemode = discord.ui.TextInput(label="Játékmód", placeholder="pl. Crystal, Netherite, SMP...", required=True, max_length=30)
    tier = discord.ui.TextInput(label="Elért Rank (LT3 vagy alatta)", placeholder="pl. LT3, LT4, LT5", required=True, max_length=10)
    is_public = discord.ui.TextInput(label="Publikus? (igen / nem)", placeholder="igen vagy nem", required=True, max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba: Hiányzó konfiguráció.", ephemeral=True)
            return

        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
        unique_id = int(time.time() * 1000)
        clean_username = self.minecraft_name.value.strip()
        clean_gamemode = self.gamemode.value.strip().lower()
        clean_rank = self.tier.value.strip().upper()
        is_pub = self.is_public.value.strip().lower() in ["igen", "i", "yes", "y"]

        payload = {
            "id": unique_id,
            "username": clean_username,
            "gamemode": clean_gamemode,
            "rank": clean_rank,
            "tester_id": str(interaction.user.id),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests"
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status in [200, 201]:
                        await interaction.followup.send(f"✅ Sikeresen rögzítve!\n* Játékos: `{clean_username}`\n* Játékmód: `{clean_gamemode}`\n* Elért Rank: `{clean_rank}`\n* Publikus: `{'Igen' if is_pub else 'Nem'}`", ephemeral=True)
                        if is_pub:
                            await send_test_announcements(interaction.client, clean_username, clean_gamemode, clean_rank, interaction.user)
                        
                        fields = [
                            ("Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                            ("Játékos", f"`{clean_username}`", True),
                            ("Játékmód", f"`{clean_gamemode}`", True),
                            ("Elért Rank", f"`{clean_rank}`", True),
                            ("Publikus", f"{'Igen' if is_pub else 'Nem'}", True)
                        ]
                        await send_log(interaction.client, "📝 Manuális Teszt Rögzítve", "Egy regulator manuálisan rögzített egy tesztet.", discord.Color.green(), fields)
                    else:
                        err = await resp.text()
                        await interaction.followup.send(f"❌ Nem sikerült menteni: {err}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt: {str(e)}", ephemeral=True)

class CooldownResetModal(discord.ui.Modal, title="Játékos Cooldown Törlése"):
    minecraft_name = discord.ui.TextInput(label="Játékos Minecraft neve", placeholder="pl. Steve123", required=True, max_length=50)
    gamemode = discord.ui.TextInput(label="Játékmód", placeholder="pl. Crystal", required=True, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba: Hiányzó konfiguráció.", ephemeral=True)
            return

        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/cooldowns?username=eq.{self.minecraft_name.value.strip()}&gamemode=eq.{self.gamemode.value.strip().lower()}"
                async with session.delete(url, headers=headers) as resp:
                    await interaction.followup.send(f"⚡ A cooldown sikeresen törölve lett **{self.minecraft_name.value}** részére a(z) `{self.gamemode.value}` módban!", ephemeral=True)
                    fields = [
                        ("Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                        ("Érintett Játékos", f"`{self.minecraft_name.value}`", True),
                        ("Játékmód", f"`{self.gamemode.value}`", True)
                    ]
                    await send_log(interaction.client, "⏱️ Cooldown Törölve", "Egy regulator törölte egy játékos cooldownját.", discord.Color.orange(), fields)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {str(e)}", ephemeral=True)

class PlayerHistoryModal(discord.ui.Modal, title="Játékos Előélet Lekérdezése"):
    minecraft_name = discord.ui.TextInput(label="Játékos Minecraft neve", placeholder="pl. Steve123", required=True, max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba.", ephemeral=True)
            return

        username = self.minecraft_name.value.strip()
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

        try:
            async with aiohttp.ClientSession() as session:
                # Tesztek lekérése
                tests_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests?username=eq.{username}&select=gamemode,rank,created_at"
                async with session.get(tests_url, headers=headers) as resp:
                    tests = await resp.json() if resp.status == 200 else []

                # Cooldownok lekérése
                cooldowns_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/cooldowns?username=eq.{username}&select=gamemode,expires_at"
                async with session.get(cooldowns_url, headers=headers) as resp:
                    cooldowns = await resp.json() if resp.status == 200 else []

            embed = discord.Embed(title=f"📜 Játékos Előélet: `{username}`", color=discord.Color.purple())
            
            # Rangok formázása
            if tests:
                tests_str = "\n".join([f"• **{t['gamemode']}**: `{t['rank']}`" for t in tests])
                embed.add_field(name="Elért Rangok", value=tests_str, inline=False)
            else:
                embed.add_field(name="Elért Rangok", value="*Nincsenek rögzített tesztek.*", inline=False)

            # Cooldownok formázása
            if cooldowns:
                cd_str = "\n".join([f"• `{cd['gamemode']}` (Lejár: {cd.get('expires_at', 'Ismeretlen')})" for cd in cooldowns])
                embed.add_field(name="Aktív Cooldownok", value=cd_str, inline=False)
            else:
                embed.add_field(name="Aktív Cooldownok", value="*Nincs aktív cooldown.*", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt: {str(e)}", ephemeral=True)

class RegulatorPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Teszt Rögzítése", style=discord.ButtonStyle.primary, custom_id="reg_panel:manual_test")
    async def manual_test_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManualTestModal())

    @discord.ui.button(label="⏱️ Cooldown Törlése", style=discord.ButtonStyle.danger, custom_id="reg_panel:clear_cooldown")
    async def clear_cooldown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CooldownResetModal())

    @discord.ui.button(label="🔍 Játékos Előélet", style=discord.ButtonStyle.secondary, custom_id="reg_panel:player_history")
    async def player_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerHistoryModal())

    @discord.ui.button(label="📊 Saját Statisztika", style=discord.ButtonStyle.success, custom_id="reg_panel:my_stats")
    async def my_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba.", ephemeral=True)
            return

        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests?tester_id=eq.{interaction.user.id}&select=gamemode,rank"
                async with session.get(url, headers=headers) as resp:
                    tests = await resp.json() if resp.status == 200 else []

            total_tests = len(tests)
            embed = discord.Embed(title=f"📊 Regulator Statisztika: {interaction.user.display_name}", color=discord.Color.gold())
            embed.add_field(name="Összes elvégzett teszt", value=f"**{total_tests}** db", inline=False)
            
            if total_tests > 0:
                modes = {}
                for t in tests:
                    modes[t['gamemode']] = modes.get(t['gamemode'], 0) + 1
                mode_str = "\n".join([f"• `{m}`: {count} db" for m, count in modes.items()])
                embed.add_field(name="Bontás játékmódonként", value=mode_str, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt: {str(e)}", ephemeral=True)

class RegulatorPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_regulator_permissions(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        has_role = any(role.name == REGULATOR_ROLE_NAME for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message("❌ Nincs jogosultságod ehhez a panelhez (szükséges rang: **Regulator**).", ephemeral=True)
            return False
        return True

    @app_commands.command(name="regulator-panel", description="Megnyitja a regulator kezelőpanelt.")
    async def regulator_panel(self, interaction: discord.Interaction):
        if not await self.check_regulator_permissions(interaction):
            return

        embed = discord.Embed(
            title="🛡️ Regulator Kezelőpanel",
            description="Üdv a vezérlőpultban! Válassz az alábbi opciók közül:\n\n"
                        "• **📝 Teszt Rögzítése:** Manuális felvitel LT3-ig.\n"
                        "• **⏱️ Cooldown Törlése:** Várakozási idő eltávolítása.\n"
                        "• **🔍 Játékos Előélet:** Rangok és cooldownok lekérdezése.\n"
                        "• **📊 Saját Statisztika:** Eddigi elvégzett tesztjeid száma.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="NeoTiers Management System")
        await interaction.response.send_message(embed=embed, view=RegulatorPanelView(), ephemeral=True)

    @app_commands.command(name="setup-regulator-panel", description="Elküldi a nyilvános regulator panelt (Admin parancs).")
    @app_commands.describe(channel="Az a csatorna, ahová a panelt küldeni kell")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_regulator_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="🛡️ Regulator Kezelőpanel",
            description="Üdv a vezérlőpultban! Válassz az alábbi opciók közül:\n\n"
                        "• **📝 Teszt Rögzítése:** Manuális felvitel LT3-ig.\n"
                        "• **⏱️ Cooldown Törlése:** Várakozási idő eltávolítása.\n"
                        "• **🔍 Játékos Előélet:** Rangok és cooldownok lekérdezése.\n"
                        "• **📊 Saját Statisztika:** Eddigi elvégzett tesztjeid száma.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="NeoTiers Management System")
        await channel.send(embed=embed, view=RegulatorPanelView())
        await interaction.response.send_message(f"✅ A regulator panel sikeresen elküldve ide: {channel.mention}!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RegulatorPanelCog(bot))
