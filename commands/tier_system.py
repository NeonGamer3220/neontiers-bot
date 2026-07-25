import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import time
import asyncio
from typing import Literal

from config import ALL_TICKET_TYPES, REGULATOR_ROLE_ID

from commands.tier_utils import (
    THEME_LIGHT_PURPLE, THEME_LIGHT_BLUE, MODE_COLORS,
    HT_TICKETS_FILE, COOLDOWN_FILE
)
from commands.tier_ui import (
    PingPanelView, OpenQueuePanelView, HTPanelView
)

# ==========================================
# RENDSZER COG ÉS PARANCSOK
# ==========================================
class TierSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ht_auto_close_task.start()

    def cog_unload(self):
        self.ht_auto_close_task.cancel()

    @tasks.loop(minutes=30)
    async def ht_auto_close_task(self):
        if not os.path.exists(HT_TICKETS_FILE): return
        try:
            with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            now = time.time()
            to_delete = []
            
            for ch_id_str, info in data.items():
                if info.get("forcekeep"): continue
                
                channel = self.bot.get_channel(int(ch_id_str))
                if not channel:
                    to_delete.append(ch_id_str)
                    continue

                last_msg_time = info.get("last_msg_time", 0)
                time_passed = now - last_msg_time
                
                if time_passed > (44 * 3600) and not info.get("warned"):
                    await channel.send(f"<@{info['owner_id']}> ⚠️ **Figyelem!** 4 óra múlva inaktivitás miatt automatikusan lezárul a csatorna. Írj egy üzenetet az újraindításhoz!")
                    info["warned"] = True
                    
                elif time_passed > (48 * 3600):
                    await channel.send("🔒 48 óra inaktivitás telt el. A csatorna bezárul...")
                    await asyncio.sleep(3)
                    await channel.delete()
                    to_delete.append(ch_id_str)

            for d in to_delete: del data[d]
            with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
        except: pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        if ("ht-" in message.channel.name or "teszt-" in message.channel.name or "ticket-" in message.channel.name) and os.path.exists(HT_TICKETS_FILE):
            try:
                with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
                ch_id = str(message.channel.id)
                if ch_id in data:
                    data[ch_id]["last_msg_time"] = time.time()
                    data[ch_id]["warned"] = False
                    with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
            except: pass

    @app_commands.command(name="pingpanel", description="Lerakja a Queue Ping kérő panelt.")
    @app_commands.describe(panel_type="Melyik játékmódokat szeretnéd látni?")
    async def pingpanel(self, interaction: discord.Interaction, panel_type: Literal['Modern', 'Legacy', 'All']):
        if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Nincs jogosultságod!", ephemeral=True)
        embed = discord.Embed(
            title="🔔 Queue Értesítések", 
            description="Kattints a gombokra, hogy megkapd az adott játékmód várólista értesítő rangját!", 
            color=discord.Color(THEME_LIGHT_BLUE)
        )
        await interaction.channel.send(embed=embed, view=PingPanelView(panel_type))
        await interaction.response.send_message("✅ Panel lerakva!", ephemeral=True)

    @app_commands.command(name="queuepanel", description="Lerakja a Teszter Várólista nyitó panelt.")
    @app_commands.describe(panel_type="Melyik játékmódokat szeretnéd látni?")
    async def queuepanel(self, interaction: discord.Interaction, panel_type: Literal['Modern', 'Legacy', 'All']):
        if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Nincs jogosultságod!", ephemeral=True)
        embed = discord.Embed(
            title="🛡️ Teszt Várólista Megnyitása", 
            description="Teszterként kattints a játékmódra a várólista megnyitásához az adott csatornában!", 
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        await interaction.channel.send(embed=embed, view=OpenQueuePanelView(panel_type))
        await interaction.response.send_message("✅ Panel lerakva!", ephemeral=True)

    @app_commands.command(name="hightestpanel", description="Lerakja a Magas Tier Kérelem panelt.")
    @app_commands.describe(panel_type="Melyik játékmódokat szeretnéd látni?")
    async def hightestpanel(self, interaction: discord.Interaction, panel_type: Literal['Modern', 'Legacy', 'All']):
        if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Nincs jogosultságod!", ephemeral=True)
        
        embed = discord.Embed(
            title="**Magas Tier Teszt Igénylés**",
            description=(
                "HT3 vagy magasabb teszthez nyiss magas tier kérelmet. A megnyitás előtt elkérem és ellenőrzöm az eredeti Minecraft nevedet.\n\n"
                "**Fontos**\nMagas tier kérelemből egyszerre legfeljebb 12 nyitott lehet.\n\n"
                "**Automatikus lezárás**\nBármilyen emberi üzenet újraindítja a 48 órás inaktivitási számlálót. Automatikus zárás előtt 4 órával figyelmeztetést küldök és megpingelem a nyitót."
            ),
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        await interaction.channel.send(embed=embed, view=HTPanelView(panel_type))
        await interaction.response.send_message("✅ Panel lerakva!", ephemeral=True)

    @app_commands.command(name="setup", description="Létrehozza a Teszter/Queue rangokat és csatornákat két kategóriában.")
    async def setup_cmd(self, interaction: discord.Interaction, modern_kategoria: discord.CategoryChannel, legacy_kategoria: discord.CategoryChannel):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)
            
        await interaction.response.defer()
        guild = interaction.guild

        try:
            for label, key, _ in ALL_TICKET_TYPES:
                color_hex = MODE_COLORS.get(key.lower(), 0x3498db)
                role_color = discord.Color(color_hex)
                
                tester_name = f"{label} Teszter"
                queue_name = f"{label} Queue"
                
                if not discord.utils.get(guild.roles, name=tester_name):
                    await guild.create_role(name=tester_name, color=role_color)
                if not discord.utils.get(guild.roles, name=queue_name):
                    await guild.create_role(name=queue_name, mentionable=True, color=role_color)
                
                await asyncio.sleep(0.5)

            await interaction.followup.send("✅ Rendszer sikeresen telepítve: Rangok létrehozva!")
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt a setup közben: `{e}`")

    @app_commands.command(name="revertsetup", description="Törli az összes setup által létrehozott rangot.")
    async def revertsetup_cmd(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)
            
        await interaction.response.defer()
        guild = interaction.guild

        try:
            for label, key, _ in ALL_TICKET_TYPES:
                tester_name = f"{label} Teszter"
                queue_name = f"{label} Queue"
                
                tester_role = discord.utils.get(guild.roles, name=tester_name)
                if tester_role: await tester_role.delete()
                
                queue_role = discord.utils.get(guild.roles, name=queue_name)
                if queue_role: await queue_role.delete()
                
                await asyncio.sleep(0.5)

            await interaction.followup.send("✅ Setup sikeresen visszavonva: Minden generált rang törölve!")
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba történt a revert közben: `{e}`")

    @app_commands.command(name="forcekeep", description="Megakadályozza a ticket automatikus törlését (Regulator).")
    async def forcekeep(self, interaction: discord.Interaction):
        if not any(r.id == REGULATOR_ROLE_ID for r in interaction.user.roles) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Nincs jogosultságod!", ephemeral=True)
            
        try:
            with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            ch_id = str(interaction.channel.id)
            if ch_id in data:
                data[ch_id]["forcekeep"] = True
                with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
                await interaction.response.send_message("🛡️ Automatikus törlés kikapcsolva erre a ticketre.")
            else:
                await interaction.response.send_message("❌ Ez nem egy regisztrált ticket.", ephemeral=True)
        except: pass

    @app_commands.command(name="ticketadd", description="Ember hozzáadása a tickethez.")
    async def tadd(self, interaction: discord.Interaction, tag: discord.Member):
        if not interaction.user.guild_permissions.administrator and not any(r.id == REGULATOR_ROLE_ID for r in interaction.user.roles): return
        await interaction.channel.set_permissions(tag, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"✅ {tag.mention} hozzáadva a csatornához.")

    @app_commands.command(name="ticketremove", description="Ember eltávolítása a ticketből.")
    async def trem(self, interaction: discord.Interaction, tag: discord.Member):
        if not interaction.user.guild_permissions.administrator and not any(r.id == REGULATOR_ROLE_ID for r in interaction.user.roles): return
        await interaction.channel.set_permissions(tag, overwrite=None)
        await interaction.response.send_message(f"✅ {tag.mention} eltávolítva a csatornából.")

    @app_commands.command(name="resetcooldown", description="Alaphelyzetbe állítja egy játékos 14 napos tesztelési cooldownját.")
    @app_commands.describe(tag="A játékos", gamemode="Játékmód (pl. sword, mace)")
    async def resetcooldown(self, interaction: discord.Interaction, tag: discord.Member, gamemode: str):
        if not interaction.user.guild_permissions.administrator and not any(r.id == REGULATOR_ROLE_ID for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Nincs jogosultságod ehhez a parancshoz!", ephemeral=True)
        
        mode_key = gamemode.lower().strip()
        
        try:
            if os.path.exists(COOLDOWN_FILE):
                with open(COOLDOWN_FILE, "r") as f:
                    data = json.load(f)
                
                p_id = str(tag.id)
                if p_id in data and mode_key in data[p_id]:
                    del data[p_id][mode_key]
                    if not data[p_id]: del data[p_id]
                        
                    with open(COOLDOWN_FILE, "w") as f: json.dump(data, f)
                    await interaction.response.send_message(f"✅ Sikeresen törölted {tag.mention} cooldownját a(z) `{mode_key}` játékmódban!", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ {tag.mention} játékosnak nincs aktív cooldownja a(z) `{mode_key}` játékmódban.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Nincs aktív cooldown fájl a rendszerben.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Hiba történt a cooldown törlése során: `{e}`", ephemeral=True)

async def setup(bot):
    bot.add_view(PingPanelView("Modern"))
    bot.add_view(PingPanelView("Legacy"))
    bot.add_view(PingPanelView("All"))
    bot.add_view(OpenQueuePanelView("Modern"))
    bot.add_view(OpenQueuePanelView("Legacy"))
    bot.add_view(OpenQueuePanelView("All"))
    bot.add_view(HTPanelView("Modern"))
    bot.add_view(HTPanelView("Legacy"))
    bot.add_view(HTPanelView("All"))
    
    await bot.add_cog(TierSystemCog(bot))
