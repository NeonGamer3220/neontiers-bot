import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import time
import json
import os
from config import SUPABASE_URL, SUPABASE_KEY, LOG_CHANNEL_ID, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID

REGULATOR_ROLE_NAME = "Regulator"
COOLDOWN_FILE = "tier_cooldowns.json"

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
    discord_id = discord.ui.TextInput(label="Játékos Discord ID-ja", placeholder="pl. 1335330940980826122", required=True, max_length=30)
    gamemode = discord.ui.TextInput(label="Játékmód", placeholder="pl. mace, sword", required=True, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        uid = self.discord_id.value.strip()
        gmode = self.gamemode.value.strip().lower()

        cd_data = load_cooldowns()
        if uid in cd_data and gmode in cd_data[uid]:
            del cd_data[uid][gmode]
            if not cd_data[uid]:
                del cd_data[uid]
            save_cooldowns(cd_data)

            await interaction.followup.send(f"⚡ A cooldown sikeresen törölve lett a(z) `{uid}` ID-hoz a(z) `{gmode}` módban!", ephemeral=True)
            fields = [
                ("Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                ("Érintett Discord ID", f"`{uid}`", True),
                ("Játékmód", f"`{gmode}`", True)
            ]
            await send_log(interaction.client, "⏱️ Cooldown Törölve", "Egy regulator törölte egy játékos cooldownját a JSON-ből.", discord.Color.orange(), fields)
        else:
            await interaction.followup.send(f"⚠️ Nem található aktív cooldown ehhez az ID-hoz és játékmódhoz a JSON-ben.", ephemeral=True)

class AddCooldownModal(discord.ui.Modal, title="Cooldown Hozzáadása (14 nap)"):
    discord_id = discord.ui.TextInput(label="Játékos Discord ID-ja", placeholder="pl. 1335330940980826122", required=True, max_length=30)
    gamemode = discord.ui.TextInput(label="Játékmód", placeholder="pl. mace, sword", required=True, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        uid = self.discord_id.value.strip()
        gmode = self.gamemode.value.strip().lower()
        
        expires_timestamp = time.time() + (14 * 24 * 60 * 60)

        cd_data = load_cooldowns()
        if uid not in cd_data:
            cd_data[uid] = {}
        cd_data[uid][gmode] = expires_timestamp
        save_cooldowns(cd_data)

        await interaction.followup.send(f"⚡ A 14 napos cooldown sikeresen rögzítve lett a(z) `{uid}` ID részére a(z) `{gmode}` játékmódban!", ephemeral=True)
        fields = [
            ("Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
            ("Érintett Discord ID", f"`{uid}`", True),
            ("Játékmód", f"`{gmode}`", True),
            ("Időtartam", "14 nap", True)
        ]
        await send_log(interaction.client, "⏱️ Cooldown Hozzáadva", "Egy regulator manuálisan 14 napos cooldown-t adott a JSON-höz.", discord.Color.orange(), fields)

class StaffReportModal(discord.ui.Modal, title="Hiba vagy Eltérés Jelentése"):
    target_info = discord.ui.TextInput(label="Érintett Játékos / Teszt / Téma", placeholder="pl. Steve123 vagy Discord ID", required=True, max_length=100)
    description = discord.ui.TextInput(label="A hiba vagy eltérés részletes leírása", placeholder="Írd le pontosan mi a probléma...", style=discord.TextStyle.paragraph, required=True, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        fields = [
            ("Bejelentő Regulator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
            ("Érintett elem", f"`{self.target_info.value.strip()}`", False),
            ("Leírás", self.description.value.strip(), False)
        ]
        await send_log(
            interaction.client,
            "⚠️ Hiba / Eltérés Jelentve",
            "Egy regulator hibát vagy adateltérést jelentett.",
            discord.Color.red(),
            fields
        )
        await interaction.followup.send("✅ A jelentés sikeresen elküldve a belső log csatornába!", ephemeral=True)

class PlayerHistoryModal(discord.ui.Modal, title="Játékos Előélet Lekérdezése"):
    minecraft_name = discord.ui.TextInput(label="Játékos Minecraft neve (Opcionális)", placeholder="pl. Steve123", required=False, max_length=50)
    discord_id = discord.ui.TextInput(label="Játékos Discord ID-ja (Opcionális)", placeholder="pl. 1335330940980826122", required=False, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        mc_name = self.minecraft_name.value.strip() if self.minecraft_name.value else None
        uid = self.discord_id.value.strip() if self.discord_id.value else None

        if not mc_name and not uid:
            await interaction.followup.send("❌ Legalább az egyik mezőt ki kell töltened (Minecraft név vagy Discord ID)!", ephemeral=True)
            return

        tests = []
        if mc_name and SUPABASE_URL and SUPABASE_KEY:
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            try:
                async with aiohttp.ClientSession() as session:
                    tests_url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests?username=eq.{mc_name}&select=gamemode,rank,created_at"
                    async with session.get(tests_url, headers=headers) as resp:
                        if resp.status == 200:
                            tests = await resp.json()
            except Exception as e:
                print(f"[HISTORY TESTS ERROR] {e}")

        user_cooldowns = {}
        if uid:
            cd_data = load_cooldowns()
            if uid in cd_data:
                user_cooldowns = cd_data[uid]

        embed = discord.Embed(title=f"📜 Játékos Előélet Lekérdezés", color=discord.Color.purple())
        if mc_name:
            embed.add_field(name="Minecraft Név", value=f"`{mc_name}`", inline=True)
        if uid:
            embed.add_field(name="Discord ID", value=f"`{uid}`", inline=True)

        if tests:
            tests_str = "\n".join([f"• **{t['gamemode']}**: `{t['rank']}`" for t in tests])
            embed.add_field(name="Elért Rangok (Supabase)", value=tests_str, inline=False)
        elif mc_name:
            embed.add_field(name="Elért Rangok (Supabase)", value="*Nincsenek rögzített tesztek ezen a néven.*", inline=False)

        if user_cooldowns:
            cd_lines = []
            for mode, timestamp in user_cooldowns.items():
                dt = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
                dt_str = dt.strftime("%Y-%m-%d %H:%M")
                cd_lines.append(f"• `{mode}` (Lejár: {dt_str} UTC)")
            embed.add_field(name="Aktív Cooldownok (JSON)", value="\n".join(cd_lines), inline=False)
        elif uid:
            embed.add_field(name="Aktív Cooldownok (JSON)", value="*Nincs aktív cooldown ennél a Discord ID-nál.*", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

class RegulatorPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # 1. Sor
    @discord.ui.button(label="📝 Teszt Rögzítése", style=discord.ButtonStyle.primary, custom_id="reg_panel:manual_test", row=0)
    async def manual_test_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManualTestModal())

    @discord.ui.button(label="⏱️ Cooldown Törlése", style=discord.ButtonStyle.danger, custom_id="reg_panel:clear_cooldown", row=0)
    async def clear_cooldown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CooldownResetModal())

    @discord.ui.button(label="🔍 Játékos Előélet", style=discord.ButtonStyle.secondary, custom_id="reg_panel:player_history", row=0)
    async def player_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerHistoryModal())

    # 2. Sor
    @discord.ui.button(label="📊 Saját Statisztika", style=discord.ButtonStyle.success, custom_id="reg_panel:my_stats", row=1)
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

    @discord.ui.button(label="⏱️ Cooldown Hozzáadása", style=discord.ButtonStyle.danger, custom_id="reg_panel:add_cooldown", row=1)
    async def add_cooldown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddCooldownModal())

    @discord.ui.button(label="⚠️ Hiba Jelentése", style=discord.ButtonStyle.secondary, custom_id="reg_panel:staff_report", row=1)
    async def staff_report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StaffReportModal())

    # 3. Sor (Szabályzat & Súgó)
    @discord.ui.button(label="📖 Szabályzat & Súgó", style=discord.ButtonStyle.primary, custom_id="reg_panel:rules", row=2)
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)

        embed = discord.Embed(
            title="📖 NeoTiers Regulator Szabályzat & Útmutató",
            description="Íme a hivatalos irányelvek és szabályok a regulatorok számára:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="1. 🛠️ Modok és Kiegészítők",
            value="• **Engedélyezett:** Low fire, Consumable Optimizer, shield status mod, és minden olyan mod ami nem ad előnyt / nem automatizálja a játékmenetet.\n"
                  "• **Tiltott:** Mouse tweaks, Dura pack, Tweakaroo, Walksy/Marlow's Crystal Optimizer, Fire Client, Hack kliensek, pinget befolyásoló modok, Multi Keybinds, Health indicator, más kitett/plusz dolgok CPVP-ben.",
            inline=False
        )
        embed.add_field(
            name="2. ⚖️ Tierlist Bannok & Büntetések",
            value="• **Csalás / Tiltott mod:** 1 hónap (+ tier wipe ha van)\n"
                  "• **Account sharing:** 3 hónap mindkét félnek (tier wipe csak annál, akinél játszottak)\n"
                  "• **Alt tesztelés:** 1 hónap (alt törölve, eredeti ban)\n"
                  "• **Boostolás / Megegyezés:** 1 hónap (+ tier wipe) | **SS / Handcam megtagadása:** 1-2 hónap\n"
                  "• **Eredmény hamisítás / Staff megtévesztése:** 1-2 hónap\n"
                  "• **Toxicitás / zaklatás:** 14 nap | **Sandbagging:** 1 hónap\n"
                  "• **Megvesztegetés / Összejátszás:** Örök ban azonnal (nincs alkalom számolás)",
            inline=False
        )
        embed.add_field(
            name="3. ⚔️ Teszt Közbeni Szabályzat",
            value="• Tilos az időhúzás és a menekülés.\n"
                  "• Mendelés / bújás / textúraváltás max 2 perc, utána a kör az ellenfélé (clip kell).\n"
                  "• Időkérés / shiftelés: állj meg, redó kérhető ha nem áll meg (clip kell).\n"
                  "• Lagg / DC: ha ledob a szerver, az ellenfélé a kör. Kifagyásnál 1 hit elnézhető, többnél redó.\n"
                  "• Free hit tilos a kör elején. FFA szervereken harmadik fél beleszólásakor: újrakezdés.",
            inline=False
        )
        embed.add_field(
            name="4. 🔄 Újratesztelés & Új Név",
            value="• Újratesztelés 14 naponta lehetséges. Első teszten max LT3.\n"
                  "• **Névváltás:** 1. Discordon: `/unlink` majd `/link` | 2. A kódot 10 percen belül beírni a `chaosffa.kinetic.host` szerveren a `/link [kód]` paranccsal.",
            inline=False
        )
        embed.add_field(
            name="5. 📊 Gamemód Követelmények & Besorolások",
            value="• **LT3 alatt alap köresetek:** Vanilla/SMP/Cart (FT4, LT3 alatt FT3), DiaSMP/OGV/NethPot/Mace/SpearMace/SpearElytra/Trident (FT4, LT3 alatt FT2), Sword/Uhc/Pot/Creeper/ShieldlessUHC (FT10, LT3 alatt FT6), Axe (FT20, LT3 alatt FT10).\n"
                  "• **Eredmény alapú tier besorolások:** (pl. Vanilla/NethPot 3-0/2-0: LT5/HT5/LT4, Sword/Pot 6-0: LT5/HT5, Axe 10-0: LT5/HT5; eval pass esetén LT3. Ha nagyobb a teszt eredmény, a teszter eltérhet).",
            inline=False
        )
        embed.add_field(
            name="6. 👴 UnRetire & Retired Rendszer",
            value="• **UnRetire:** Indulás a retire tierből. 75% winrate kell az azonos tierű ellen, ha nem sikerül, lefelé haladva HT3-ig. Ha ott sem, maradhat a retire vagy megy sima eval tesztre.\n"
                  "• **Retired feltételek:** Min. LT2 rang. 2 defenset kell szerezni saját tieredbeli vagy feljebb pályázó játékos legyőzésével (75% winrate). Az elmúlt 2 hónapban nem lehetett magasabb tier próbálkozásod.\n"
                  "• **Időtartamok:** LT2/HT2: 2 védelem + 40+ nap | LT1: 2 védelem + 60+ nap | HT1: 3 védelem + 90+ nap.",
            inline=False
        )
        embed.add_field(
            name="7. ⚠️ Hiba Jelentése",
            value="• Ha hibás adatot vagy eltérést találsz az adatbázisban, ne szerkeszd önhatalmúlag, hanem használd a panelen lévő **⚠️ Hiba Jelentése** gombot a logoláshoz!",
            inline=False
        )
        embed.set_footer(text="NeoTiers Management System")
        await interaction.followup.send(embed=embed, ephemeral=True)

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
                        "• **⏱️ Cooldown Törlése:** Várakozási idő eltávolítása (JSON).\n"
                        "• **🔍 Játékos Előélet:** Rangok és cooldownok lekérdezése.\n"
                        "• **📊 Saját Statisztika:** Eddigi elvégzett tesztjeid száma.\n"
                        "• **⏱️ Cooldown Hozzáadása:** 14 napos eltiltás rögzítése (JSON).\n"
                        "• **⚠️ Hiba Jelentése:** Hibák vagy eltérések beküldése a logba.\n"
                        "• **📖 Szabályzat & Súgó:** A hivatalos szabályzat megtekintése.",
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
                        "• **⏱️ Cooldown Törlése:** Várakozási idő eltávolítása (JSON).\n"
                        "• **🔍 Játékos Előélet:** Rangok és cooldownok lekérdezése.\n"
                        "• **📊 Saját Statisztika:** Eddigi elvégzett tesztjeid száma.\n"
                        "• **⏱️ Cooldown Hozzáadása:** 14 napos eltiltás rögzítése (JSON).\n"
                        "• **⚠️ Hiba Jelentése:** Hibák vagy eltérések beküldése a logba.\n"
                        "• **📖 Szabályzat & Súgó:** A hivatalos szabályzat megtekintése.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="NeoTiers Management System")
        await channel.send(embed=embed, view=RegulatorPanelView())
        await interaction.response.send_message(f"✅ A regulator panel sikeresen elküldve ide: {channel.mention}!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RegulatorPanelCog(bot))
