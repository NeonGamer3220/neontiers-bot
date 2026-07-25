import discord
import os
import json
import time
import asyncio
import datetime

from config import (
    TICKET_TYPES, LEGACY_TICKET_TYPES, ALL_TICKET_TYPES,
    REGULATOR_ROLE_ID, STAFF_ROLE_ID, TIER_RESULTS_CHANNEL_ID,
    get_gamemode_display_name, POINTS
)
from commands.ban_enforcement import is_banned_by_role
from database import get_linked_minecraft_name_async, supabase_select

from commands.tier_utils import (
    THEME_LIGHT_PURPLE, THEME_LIGHT_BLUE,
    HT_TICKETS_FILE, ACTIVE_QUEUES, VALID_HT_TIERS, ALLOWED_QUEUE_TIERS,
    save_test_result_supabase, get_cooldown, set_cooldown,
    check_timeout, get_ticket_category, update_queue_message
)

# ==========================================
# TESZT EREDMÉNY RÖGZÍTŐ RENDSZER (MODAL)
# ==========================================
class TierResultModal(discord.ui.Modal, title="Teszt Eredmény Rögzítése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, tester_id: int, queue_ch_id: int = None):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.tester_id = tester_id
        self.queue_ch_id = queue_ch_id
        
        self.tier_input = discord.ui.TextInput(
            label="Szerzett Tier (max. LT3 adható)",
            placeholder="Pl.: LT3",
            required=True,
            max_length=10
        )
        self.add_item(self.tier_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_tier = self.tier_input.value.strip().upper()
        if new_tier == "UNRANKED" or new_tier == "500": new_tier = "Unranked"
        
        if new_tier.upper() not in ALLOWED_QUEUE_TIERS:
            return await interaction.response.send_message("❌ Várólista tesztből **maximum LT3** adható, és Retired (R) rangok sem állíthatók be!", ephemeral=True)
            
        await interaction.response.defer()
        
        mode_display = get_gamemode_display_name(self.gamemode)
        pts = POINTS.get(new_tier, 0)
        
        player_tests = supabase_select("tests", "username", self.player_mc)
        existing_id = None
        user_tiers = {}
        for t in player_tests:
            gmode = str(t.get("gamemode", "")).strip().lower()
            user_tiers[gmode] = str(t.get("rank", "Unranked"))
            if gmode == mode_display.lower():
                existing_id = t.get("id")

        await save_test_result_supabase(self.player_mc, mode_display, new_tier, pts, existing_id)

        user_tiers[mode_display.lower()] = new_tier

        log_embed = discord.Embed(
            title="Teszt Eredmény",
            description=f"<@{self.tester_id}> **{new_tier}** tiert adott `{self.player_mc}` játékosnak **{mode_display}** játékmódból.",
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        log_embed.set_thumbnail(url=f"https://minotar.net/helm/{self.player_mc}/256.png")
        
        for label, key, emoji_raw in ALL_TICKET_TYPES:
            tier_val = user_tiers.get(label.lower(), "Unranked")
            emoji_str = str(emoji_raw)
            if emoji_str.isdigit():
                safe_name = label.replace(" ", "").replace("-", "")
                emoji_str = f"<:{safe_name}:{emoji_str}>"
            log_embed.add_field(name=f"{emoji_str} {label}", value=f"**{tier_val}**", inline=True)

        rem = len(ALL_TICKET_TYPES) % 3
        if rem != 0:
            for _ in range(3 - rem):
                log_embed.add_field(name="\u200b", value="\u200b", inline=True)

        log_embed.set_footer(text=f"Időpont: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if TIER_RESULTS_CHANNEL_ID:
            log_channel = interaction.guild.get_channel(TIER_RESULTS_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=log_embed)

        try:
            with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            if str(interaction.channel.id) in data:
                del data[str(interaction.channel.id)]
                with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
        except: pass

        if self.queue_ch_id and self.queue_ch_id in ACTIVE_QUEUES:
            q_data = ACTIVE_QUEUES[self.queue_ch_id]
            q_data["players"] = [p for p in q_data["players"] if p["id"] != self.player_id]
            queue_ch = interaction.guild.get_channel(self.queue_ch_id)
            if queue_ch and q_data.get("msg_id"):
                try:
                    msg = await queue_ch.fetch_message(q_data["msg_id"])
                    await update_queue_message(msg, q_data, self.gamemode)
                except: pass

        await interaction.followup.send("✅ Eredmény sikeresen rögzítve! A csatorna 5 másodperc múlva törlődik.")
        await asyncio.sleep(5)
        await interaction.channel.delete()

# ==========================================
# PRIVÁT TESZT CSATORNA GOMBOK (KÖVETKEZŐ UTÁN)
# ==========================================
class QueueTestView(discord.ui.View):
    def __init__(self, tester_id: int, player_id: int, player_mc: str, gamemode: str, queue_ch_id: int = None):
        super().__init__(timeout=None)
        self.tester_id = tester_id
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.queue_ch_id = queue_ch_id

    @discord.ui.button(label="Eredmény rögzítése", style=discord.ButtonStyle.success, custom_id="qt_result")
    async def result_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.tester_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak a teszter (vagy Admin) rögzítheti az eredményt!", ephemeral=True)
        await interaction.response.send_modal(TierResultModal(self.player_id, self.player_mc, self.gamemode, self.tester_id, self.queue_ch_id))

    @discord.ui.button(label="Ticket lezárása", style=discord.ButtonStyle.danger, custom_id="qt_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.tester_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak a teszter (vagy Admin) zárhatja le a ticketet!", ephemeral=True)
            
        await interaction.response.send_message("🔒 Ticket lezárása 5 másodperc múlva...")
        
        if self.queue_ch_id and self.queue_ch_id in ACTIVE_QUEUES:
            q_data = ACTIVE_QUEUES[self.queue_ch_id]
            q_data["players"] = [p for p in q_data["players"] if p["id"] != self.player_id]
            queue_ch = interaction.guild.get_channel(self.queue_ch_id)
            if queue_ch and q_data.get("msg_id"):
                try:
                    msg = await queue_ch.fetch_message(q_data["msg_id"])
                    await update_queue_message(msg, q_data, self.gamemode)
                except: pass

        await asyncio.sleep(5)
        
        try:
            with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            if str(interaction.channel.id) in data:
                del data[str(interaction.channel.id)]
                with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
        except: pass
        
        await interaction.channel.delete()

# ==========================================
# AKTÍV QUEUE NÉZET ÉS BELEPÉS/KÖVETKEZŐ/LEZÁRÁS
# ==========================================
class QueueActiveView(discord.ui.View):
    def __init__(self, gamemode: str, tester_role: discord.Role):
        super().__init__(timeout=None)
        self.gamemode = gamemode
        self.tester_role = tester_role

    @discord.ui.button(label="Belépés / Kilépés (Játékos)", style=discord.ButtonStyle.primary, custom_id="q_player_toggle")
    async def toggle_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if is_banned_by_role(interaction.user):
            return await interaction.followup.send("❌ Ki vagy tiltva, nem léphetsz be a várólistába!", ephemeral=True)

        if check_timeout(interaction.user.id):
            return await interaction.followup.send("❌ Inaktivitáson (Timeout) vagy!", ephemeral=True)
            
        cd = get_cooldown(interaction.user.id, self.gamemode)
        if time.time() < cd:
            return await interaction.followup.send(f"⏳ Cooldownon vagy! Lejár: <t:{int(cd)}:R>", ephemeral=True)

        q_data = ACTIVE_QUEUES.get(interaction.channel.id)
        if not q_data: return await interaction.followup.send("❌ Ez a queue már lezárult.", ephemeral=True)

        player_exists = any(p["id"] == interaction.user.id for p in q_data["players"])
        if player_exists:
            q_data["players"] = [p for p in q_data["players"] if p["id"] != interaction.user.id]
            await interaction.followup.send("Kiléptél a várólistáról.", ephemeral=True)
        else:
            if len(q_data["players"]) >= 20:
                return await interaction.followup.send("❌ A várólista betelt (20/20)!", ephemeral=True)
                
            mc_name = await get_linked_minecraft_name_async(interaction.user.id)
            if not mc_name:
                return await interaction.followup.send("❌ Nincs Minecraft fiókod linkelve!", ephemeral=True)
                
            q_data["players"].append({"id": interaction.user.id, "mc": mc_name, "status": "VÁR"})
            await interaction.followup.send("Beléptél a várólistára!", ephemeral=True)
        
        await update_queue_message(interaction.message, q_data, self.gamemode)

    @discord.ui.button(label="Következő", style=discord.ButtonStyle.success, custom_id="q_tester_next")
    async def next_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if self.tester_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("❌ Nincs Teszter rangod ehhez a módhoz!", ephemeral=True)

        q_data = ACTIVE_QUEUES.get(interaction.channel.id)
        if not q_data or not q_data["players"]:
            return await interaction.followup.send("❌ Nincs több játékos a várólistán!", ephemeral=True)

        target_p = None
        for p in q_data["players"]:
            if p["status"] == "VÁR":
                target_p = p
                break
                
        if not target_p:
            return await interaction.followup.send("❌ Nincs olyan játékos a várólistán, aki épp nem tesztelődik!", ephemeral=True)

        target_p["status"] = "TESZT"
        await update_queue_message(interaction.message, q_data, self.gamemode)

        player = interaction.guild.get_member(target_p["id"])
        if not player: 
            return await interaction.followup.send("❌ A játékos már nincs a szerveren.", ephemeral=True)

        category = get_ticket_category(interaction.guild, self.gamemode) or interaction.channel.category

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            player: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        staff = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff: overwrites[staff] = discord.PermissionOverwrite(view_channel=True)

        channel = await interaction.guild.create_text_channel(
            name=f"teszt-{self.gamemode}-{player.name[:6]}",
            category=category,
            overwrites=overwrites
        )
        
        display_name = get_gamemode_display_name(self.gamemode)
        
        embed = discord.Embed(
            title=f"**{display_name} várólista teszt - {target_p['mc']}**",
            description=(
                f"Minecraft név: `{target_p['mc']}` Discord: {player.mention} Játékmód: **{display_name}**\n\n"
                f"**Inaktivitás**\n"
                f"Bármilyen emberi üzenet újraindítja a 48 órás számlálót. Automatikus zárás előtt 4 órával figyelmeztetést küldök.\n\n"
                f"Ha végeztetek, a kérelmet a teszter zárhatja le, utána a csatorna törlődik."
            ),
            color=discord.Color(THEME_LIGHT_BLUE)
        )
        
        await channel.send(content=f"{player.mention} {interaction.user.mention}", embed=embed, view=QueueTestView(interaction.user.id, player.id, target_p['mc'], self.gamemode, interaction.channel.id))
        set_cooldown(player.id, self.gamemode)
        
        data = {}
        if os.path.exists(HT_TICKETS_FILE):
            try:
                with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            except: pass
        data[str(channel.id)] = {"owner_id": player.id, "last_msg_time": time.time(), "warned": False, "forcekeep": False}
        with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
        
        await interaction.followup.send(f"✅ Teszt szoba létrehozva: {channel.mention}", ephemeral=True)

    @discord.ui.button(label="Lezárás", style=discord.ButtonStyle.danger, custom_id="q_tester_close")
    async def close_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if self.tester_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("❌ Ezt csak teszterek használhatják!", ephemeral=True)
            
        ACTIVE_QUEUES.pop(interaction.channel.id, None)
        await interaction.followup.send("🧹 A Queue lezárult, a csatorna 5 másodperc múlva törlődik...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Queue lezárva {interaction.user.display_name} által.")
        except: pass

# ==========================================
# MAGAS TIER KÉRELEM (HT TICKET)
# ==========================================
class HTSuggestionModal(discord.ui.Modal, title="Tier Javaslat beküldése"):
    def __init__(self, player_mc: str, gamemode: str):
        super().__init__()
        self.player_mc = player_mc
        self.gamemode = gamemode
        
        self.tier = discord.ui.TextInput(label="Javasolt Tier (pl. LT3, HT2)", placeholder="LT3", required=True, max_length=4)
        self.add_item(self.tier)

    async def on_submit(self, interaction: discord.Interaction):
        reg_ping = f"<@&{REGULATOR_ROLE_ID}>" if REGULATOR_ROLE_ID else "@Regulator"
        embed = discord.Embed(title="📊 Tier Javaslat", color=discord.Color(THEME_LIGHT_PURPLE))
        embed.add_field(name="Játékos", value=self.player_mc)
        embed.add_field(name="Játékmód", value=get_gamemode_display_name(self.gamemode))
        embed.add_field(name="Javaslat", value=self.tier.value)
        embed.set_footer(text=f"Javasolta: {interaction.user.display_name}")
        
        await interaction.response.send_message(content=f"{reg_ping} Új tier javaslat érkezett ellenőrzésre!", embed=embed)

class HTTicketView(discord.ui.View):
    def __init__(self, owner_id: int, gamemode: str, player_mc: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.gamemode = gamemode
        self.player_mc = player_mc

    @discord.ui.button(label="Javaslat rögzítése", style=discord.ButtonStyle.success, custom_id="ht_suggest")
    async def suggest_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HTSuggestionModal(self.player_mc, self.gamemode))

    @discord.ui.button(label="Ticket Lezárása", style=discord.ButtonStyle.danger, custom_id="ht_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_reg = any(r.id == REGULATOR_ROLE_ID for r in interaction.user.roles)
        if interaction.user.id != self.owner_id and not is_reg and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak a nyitó vagy egy Regulátor zárhatja be!", ephemeral=True)
            
        await interaction.response.send_message("🔒 Ticket zárása 5 másodperc múlva...")
        await asyncio.sleep(5)
        
        try:
            with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            if str(interaction.channel.id) in data:
                del data[str(interaction.channel.id)]
                with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)
        except: pass
        
        await interaction.channel.delete()

class HTRequestButton(discord.ui.Button):
    def __init__(self, label: str, mode_key: str, emoji_raw: str):
        emoji_str = str(emoji_raw)
        if emoji_str.isdigit():
            safe_name = label.replace(" ", "").replace("-", "")
            emoji_str = f"<:{safe_name}:{emoji_str}>"
        super().__init__(label=label, emoji=emoji_str, style=discord.ButtonStyle.danger, custom_id=f"ht_btn_{mode_key}")
        self.mode_key = mode_key
        self.mode_label = label

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if is_banned_by_role(interaction.user):
            return await interaction.followup.send("❌ Ki vagy tiltva, nem nyithatsz magas tier kérelmet!", ephemeral=True)

        if os.path.exists(HT_TICKETS_FILE):
            try:
                with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
                if len(data) >= 12:
                    return await interaction.followup.send("❌ Jelenleg elérte a szerver a maximális 12 nyitott magas tier kérelmet. Kérlek próbáld újra később!", ephemeral=True)
            except: pass

        if check_timeout(interaction.user.id):
            return await interaction.followup.send("❌ Inaktivitáson (Timeout) vagy!", ephemeral=True)
            
        mc_name = await get_linked_minecraft_name_async(interaction.user.id)
        if not mc_name:
            return await interaction.followup.send("❌ Nincs Minecraft fiókod linkelve!", ephemeral=True)

        player_tests = supabase_select("tests", "username", mc_name)
        mode_display = get_gamemode_display_name(self.mode_key)
        
        current_tier = "Unranked"
        for t in player_tests:
            if str(t.get("gamemode", "")).strip().lower() == mode_display.lower():
                current_tier = str(t.get("rank", "Unranked")).upper()
                break

        if current_tier not in VALID_HT_TIERS:
            return await interaction.followup.send(f"❌ Csak akkor nyithatsz magas tesztet, ha legalább **LT3** vagy a(z) `{self.mode_label}` játékmódban! (Jelenlegi szinted: {current_tier})", ephemeral=True)

        category = get_ticket_category(interaction.guild, self.mode_key)
        ch_name = f"ht-{self.mode_key}-{interaction.user.name[:6]}"
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
        }
        reg_role = interaction.guild.get_role(REGULATOR_ROLE_ID)
        if reg_role:
            overwrites[reg_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
            
        channel = await interaction.guild.create_text_channel(
            name=ch_name, category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="**Magas Tier Teszt**", 
            description=(
                f"Nyitotta: {interaction.user.mention}\n"
                f"Minecraft neved: `{mc_name}` Játékmód: **{self.mode_label}**\n\n"
                f"**Inaktivitás**\n"
                f"Bármilyen emberi üzenet újraindítja a 48 órás számlálót. Automatikus zárás előtt 4 órával figyelmeztetést küldök.\n\n"
                f"Ha végeztetek, a kérelmet staff zárhatja le, utána a csatorna törlődik."
            ), 
            color=discord.Color(THEME_LIGHT_BLUE)
        )
        
        await channel.send(embed=embed, view=HTTicketView(interaction.user.id, self.mode_key, mc_name))
        
        data = {}
        if os.path.exists(HT_TICKETS_FILE):
            try:
                with open(HT_TICKETS_FILE, "r") as f: data = json.load(f)
            except: pass
        data[str(channel.id)] = {"owner_id": interaction.user.id, "last_msg_time": time.time(), "warned": False, "forcekeep": False}
        with open(HT_TICKETS_FILE, "w") as f: json.dump(data, f)

        await interaction.followup.send(f"✅ Magas tier kérelem létrehozva: {channel.mention}", ephemeral=True)

class HTPanelView(discord.ui.View):
    def __init__(self, panel_type: str):
        super().__init__(timeout=None)
        modes = TICKET_TYPES if panel_type == "Modern" else (LEGACY_TICKET_TYPES if panel_type == "Legacy" else ALL_TICKET_TYPES)
        for label, key, emoji in modes:
            self.add_item(HTRequestButton(label, key, emoji))

# ==========================================
# GOMBOS PANELEK (PING, QUEUE INDÍTÓ)
# ==========================================
class PingRoleButton(discord.ui.Button):
    def __init__(self, label: str, mode_key: str, emoji_raw: str):
        emoji_str = str(emoji_raw)
        if emoji_str.isdigit():
            safe_name = label.replace(" ", "").replace("-", "")
            emoji_str = f"<:{safe_name}:{emoji_str}>"
        super().__init__(label=label, emoji=emoji_str, style=discord.ButtonStyle.secondary, custom_id=f"ping_btn_{mode_key}")
        self.mode_label = label

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        role_name = f"{self.mode_label} Queue"
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            return await interaction.followup.send(f"❌ A(z) **{role_name}** rang nem létezik. Setupold a szervert!", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.followup.send(f"❌ **{role_name}** értesítések kikapcsolva!", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.followup.send(f"✅ **{role_name}** értesítések bekapcsolva!", ephemeral=True)

class PingPanelView(discord.ui.View):
    def __init__(self, panel_type: str):
        super().__init__(timeout=None)
        modes = TICKET_TYPES if panel_type == "Modern" else (LEGACY_TICKET_TYPES if panel_type == "Legacy" else ALL_TICKET_TYPES)
        for label, key, emoji in modes:
            self.add_item(PingRoleButton(label, key, emoji))

class OpenQueueButton(discord.ui.Button):
    def __init__(self, label: str, mode_key: str, emoji_raw: str):
        emoji_str = str(emoji_raw)
        if emoji_str.isdigit():
            safe_name = label.replace(" ", "").replace("-", "")
            emoji_str = f"<:{safe_name}:{emoji_str}>"
        super().__init__(label=label, emoji=emoji_str, style=discord.ButtonStyle.primary, custom_id=f"oq_btn_{mode_key}")
        self.mode_key = mode_key
        self.mode_label = label
        self.emoji_str = emoji_str

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tester_role = discord.utils.get(interaction.guild.roles, name=f"{self.mode_label} Teszter")
        if not tester_role or (tester_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator):
            return await interaction.followup.send(f"❌ Nincs '{self.mode_label} Teszter' rangod!", ephemeral=True)

        category = get_ticket_category(interaction.guild, self.mode_key) or interaction.channel.category
        ch_name = f"⏳-{self.mode_label.lower().replace(' ', '-')}"

        try:
            queue_chan = await interaction.guild.create_text_channel(
                name=ch_name,
                category=category,
                reason=f"Queue nyitva: {self.mode_label} ({interaction.user.display_name})"
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Nem sikerült csatornát létrehozni: `{e}`", ephemeral=True)

        queue_role = discord.utils.get(interaction.guild.roles, name=f"{self.mode_label} Queue")
        q_ping = queue_role.mention if queue_role else f"@{self.mode_label} Queue"

        ACTIVE_QUEUES[queue_chan.id] = {
            "players": [], 
            "testers": [interaction.user.id], 
            "gamemode": self.mode_key,
            "msg_id": None
        }

        desc = f"**Helyek:** 0/20\n\n**Játékosok a várólistán:**\n*- Üres -*\n\n**Aktív Teszterek:**\n🛡️ <@{interaction.user.id}>\n"
        embed = discord.Embed(
            title=f"{self.emoji_str} {self.mode_label} Várólista", 
            description=desc, 
            color=discord.Color(THEME_LIGHT_BLUE)
        )
        
        msg = await queue_chan.send(content=f"🔔 {q_ping}", embed=embed, view=QueueActiveView(self.mode_key, tester_role))
        ACTIVE_QUEUES[queue_chan.id]["msg_id"] = msg.id
        await interaction.followup.send(f"✅ Várólista csatorna megnyitva: {queue_chan.mention}", ephemeral=True)

class OpenQueuePanelView(discord.ui.View):
    def __init__(self, panel_type: str):
        super().__init__(timeout=None)
        modes = TICKET_TYPES if panel_type == "Modern" else (LEGACY_TICKET_TYPES if panel_type == "Legacy" else ALL_TICKET_TYPES)
        for label, key, emoji in modes:
            self.add_item(OpenQueueButton(label, key, emoji))
