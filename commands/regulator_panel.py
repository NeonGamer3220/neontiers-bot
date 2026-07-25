import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import time
from config import SUPABASE_URL, SUPABASE_KEY, LOG_CHANNEL_ID, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID

REGULATOR_ROLE_NAME = "Regulator"  # Szükség esetén módosítható a rang neve

async def send_test_announcements(bot: discord.Client, username: str, gamemode: str, rank: str, tester: discord.User):
    """Elküldi a teszt eredményt a modern és a legacy eredmény csatornákba is tiszta formátumban"""
    
    # 1. Modern eredmény csatorna
    if MODERN_RESULT_CHANNEL_ID:
        try:
            channel = bot.get_channel(MODERN_RESULT_CHANNEL_ID)
            if not channel:
                channel = await bot.fetch_channel(MODERN_RESULT_CHANNEL_ID)
            
            if channel:
                embed = discord.Embed(
                    title="🏆 Új Tier Teszt Eredmény",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Játékos", value=f"`{username}`", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{rank}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Official Tiers")
                
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[MODERN RESULT ERROR] Nem sikerült elküldeni: {e}")

    # 2. Legacy eredmény csatorna
    if LEGACY_RESULT_CHANNEL_ID:
        try:
            channel = bot.get_channel(LEGACY_RESULT_CHANNEL_ID)
            if not channel:
                channel = await bot.fetch_channel(LEGACY_RESULT_CHANNEL_ID)
            
            if channel:
                embed = discord.Embed(
                    title="🏆 Új Tier Teszt Eredmény (Legacy)",
                    color=discord.Color.dark_blue(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Játékos", value=f"`{username}`", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{rank}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Legacy Tiers")
                
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[LEGACY RESULT ERROR] Nem sikerült elküldeni: {e}")

async def send_log(bot: discord.Client, title: str, description: str, color: discord.Color, fields: list = None):
    """Segédfüggvény a belső staff audit logokhoz"""
    if not LOG_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        
        if channel:
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            if fields:
                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)
            embed.set_footer(text="NeoTiers Audit Log")
            await channel.send(embed=embed)
    except Exception as e:
        print(f"[LOG ERROR] Nem sikerült logolni a csatornába: {e}")

class ManualTestModal(discord.ui.Modal, title="Manuális Teszt Rögzítés (LT3-ig)"):
    minecraft_name = discord.ui.TextInput(
        label="Játékos Minecraft neve",
        placeholder="pl. Steve123",
        required=True,
        max_length=50
    )
    gamemode = discord.ui.TextInput(
        label="Játékmód",
        placeholder="pl. Crystal, Netherite, SMP...",
        required=True,
        max_length=30
    )
    tier = discord.ui.TextInput(
        label="Elért Rank (LT3 vagy alatta)",
        placeholder="pl. LT3, LT4, LT5",
        required=True,
        max_length=10
    )
    is_public = discord.ui.TextInput(
        label="Publikus? (igen / nem)",
        placeholder="igen vagy nem",
        required=True,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba: Hiányzó konfiguráció.", ephemeral=True)
            return

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }

        unique_id = int(time.time() * 1000)
        clean_username = self.minecraft_name.value.strip()
        clean_gamemode = self.gamemode.value.strip().lower()
        clean_rank = self.tier.value.strip().upper()
        
        public_val = self.is_public.value.strip().lower()
        is_pub = public_val in ["igen", "i", "yes", "y"]

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
                        # 1. Válasz a regulatornak
                        await interaction.followup.send(
                            f"✅ Sikeresen rögzítve!\n* Játékos: `{clean_username}`\n* Játékmód: `{clean_gamemode}`\n* Elért Rank: `{clean_rank}`\n* Publikus: `{'Igen' if is_pub else 'Nem'}`",
                            ephemeral=True
                        )

                        # 2. Eredmények küldése a csatornákba CSAK HA publikus
                        if is_pub:
                            await send_test_announcements(interaction.client, clean_username, clean_gamemode, clean_rank, interaction.user)

                        # 3. Belső staff audit log
                        fields = [
                            ("Regulator / Teszter", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                            ("Játékos", f"`{clean_username}`", True),
                            ("Játékmód", f"`{clean_gamemode}`", True),
                            ("Elért Rank", f"`{clean_rank}`", True),
                            ("Publikus", f"{'Igen' if is_pub else 'Nem'}", True)
                        ]
                        await send_log(
                            interaction.client,
                            "📝 Manuális Teszt Rögzítve",
                            f"Egy regulator manuálisan rögzített egy tesztet az adatbázisba.",
                            discord.Color.green(),
                            fields
                        )
                    else:
                        err_text = await resp.text()
                        await interaction.followup.send(f"❌ Nem sikerült menteni az adatbázisba: {err_text}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt: {str(e)}", ephemeral=True)


class CooldownResetModal(discord.ui.Modal, title="Játékos Cooldown Törlése"):
    minecraft_name = discord.ui.TextInput(
        label="Játékos Minecraft neve",
        placeholder="pl. Steve123",
        required=True,
        max_length=50
    )
    gamemode = discord.ui.TextInput(
        label="Játékmód",
        placeholder="pl. Crystal",
        required=True,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ Adatbázis hiba: Hiányzó konfiguráció.", ephemeral=True)
            return

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/cooldowns?username=eq.{self.minecraft_name.value.strip()}&gamemode=eq.{self.gamemode.value.strip().lower()}"
                
                async with session.delete(url, headers=headers) as resp:
                    await interaction.followup.send(
                        f"⚡ A cooldown sikeresen törölve lett **{self.minecraft_name.value}** részére a(z) `{self.gamemode.value}` játékmódban!",
                        ephemeral=True
                    )

                    fields = [
                        ("Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                        ("Érintett Játékos", f"`{self.minecraft_name.value}`", True),
                        ("Játékmód", f"`{self.gamemode.value}`", True)
                    ]
                    await send_log(
                        interaction.client,
                        "⏱️ Cooldown Törölve",
                        f"Egy regulator manuálisan törölte egy játékos cooldownját.",
                        discord.Color.orange(),
                        fields
                    )
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt a cooldown törlésekor: {str(e)}", ephemeral=True)


class RegulatorPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Teszt Rögzítése (LT3-ig)", style=discord.ButtonStyle.primary, custom_id="reg_panel:manual_test")
    async def manual_test_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManualTestModal())

    @discord.ui.button(label="⏱️ Cooldown Törlése", style=discord.ButtonStyle.danger, custom_id="reg_panel:clear_cooldown")
    async def clear_cooldown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CooldownResetModal())


class RegulatorPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_regulator_permissions(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        
        has_role = any(role.name == REGULATOR_ROLE_NAME for role in interaction.user.roles)
        if not has_role:
            await interaction.response.send_message("❌ Nincs jogosultságod ennek a panelnek a használatához (szükséges rang: **Regulator**).", ephemeral=True)
            return False
        return True

    @app_commands.command(name="regulator-panel", description="Megnyitja a regulator kezelőpanelt (teszt rögzítés, cooldown törlés).")
    async def regulator_panel(self, interaction: discord.Interaction):
        if not await self.check_regulator_permissions(interaction):
            return

        embed = discord.Embed(
            title="🛡️ Regulator Kezelőpanel",
            description="Üdv a regulator vezérlőpultban!\nVálassz az alábbi opciók közül a gombok megnyomásával:\n\n"
                        "• **📝 Teszt Rögzítése:** Manuálisan felvihetsz egy tesztet LT3-ig.\n"
                        "• **⏱️ Cooldown Törlése:** Eltávolíthatod egy játékos várakozási idejét egy adott játékmódban.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="NeoTiers Management System")

        await interaction.response.send_message(embed=embed, view=RegulatorPanelView(), ephemeral=True)

    @app_commands.command(name="setup-regulator-panel", description="Elküldi a nyilvános regulator panelt a megadott csatornába (Admin parancs).")
    @app_commands.describe(channel="Az a csatorna, ahová a panelt küldeni kell")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_regulator_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="🛡️ Regulator Kezelőpanel",
            description="Üdv a regulator vezérlőpultban!\nVálassz az alábbi opciók közül a gombok megnyomásával:\n\n"
                        "• **📝 Teszt Rögzítése:** Manuálisan felvihetsz egy tesztet LT3-ig.\n"
                        "• **⏱️ Cooldown Törlése:** Eltávolíthatod egy játékos várakozási idejét egy adott játékmódban.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="NeoTiers Management System")

        await channel.send(embed=embed, view=RegulatorPanelView())
        await interaction.response.send_message(f"✅ A regulator panel sikeresen elküldve ide: {channel.mention}!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RegulatorPanelCog(bot))
