"""
NeonTiers Bot - Tier UI & Modals (commands/tier_ui.py)
Legördülő menük, 3 gombos várólista és High Test privát ticket kezelés.
"""

import discord
import asyncio
import time
from config import TICKET_TYPES, LEGACY_TICKET_TYPES, ALL_TICKET_TYPES, get_gamemode_display_name, STAFF_ROLE_ID, REGULATOR_ROLE_ID
from commands.tier_utils import (
    ACTIVE_QUEUES, VALID_HT_TIERS, get_ticket_category, get_queue_category, 
    update_queue_message, set_cooldown, check_timeout, THEME_LIGHT_PURPLE
)
from commands.ban_enforcement import is_banned_by_role
from database import get_linked_minecraft_name_async, save_test_result_supabase


class TestResultModal(discord.ui.Modal, title="Teszt Eredmény Rögzítése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, queue_ch_id: int = None):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.queue_ch_id = queue_ch_id

        self.tier_input = discord.ui.TextInput(
            label="Elért Szint (Tier)",
            placeholder="pl. LT3, HT2, Unranked",
            required=True,
            max_length=20
        )
        self.add_item(self.tier_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tier = self.tier_input.value.strip().upper()
        if tier not in VALID_HT_TIERS and tier != "UNRANKED":
            return await interaction.followup.send(f"❌ Érvénytelen tier formátum: `{tier}`. Használhatók: HT1-LT5, Unranked", ephemeral=True)

        guild = interaction.guild
        player_user = guild.get_member(self.player_id) or await guild.fetch_member(self.player_id)
        tester_user = interaction.user

        try:
            await save_test_result_supabase(player_user, self.player_mc, self.gamemode, tier, tester_user, interaction)
        except Exception:
            pass

        set_cooldown(self.player_id, self.gamemode, 3600)

        if self.queue_ch_id and self.queue_ch_id in ACTIVE_QUEUES:
            q_data = ACTIVE_QUEUES[self.queue_ch_id]
            q_data["players"] = [p for p in q_data["players"] if p["id"] != self.player_id]
            try:
                chan = guild.get_channel(self.queue_ch_id)
                if chan and q_data.get("msg_id"):
                    msg = await chan.fetch_message(q_data["msg_id"])
                    await update_queue_message(msg, q_data, self.gamemode)
            except Exception:
                pass

        await interaction.followup.send(f"✅ Sikeresen rögzítve! Játékos: **{self.player_mc}** | Szint: **{tier}**", ephemeral=True)
        
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Teszt befejezve: {tester_user.display_name}")
        except Exception:
            pass


class TestTicketView(discord.ui.View):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, queue_ch_id: int = None):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.queue_ch_id = queue_ch_id

    @discord.ui.button(label="📝 Eredmény Rögzítése", style=discord.ButtonStyle.green, custom_id="test_record_result")
    async def record_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff:
            return await interaction.response.send_message("❌ Csak teszterek vagy regulatorok rögzíthetnek eredményt!", ephemeral=True)

        modal = TestResultModal(
            player_id=self.player_id,
            player_mc=self.player_mc,
            gamemode=self.gamemode,
            queue_ch_id=self.queue_ch_id
        )
        await interaction.response.send_modal(modal)


class QueueActiveView(discord.ui.View):
    def __init__(self, mode_key: str, tester_role: discord.Role, is_legacy: bool):
        super().__init__(timeout=None)
        self.mode_key = mode_key
        self.tester_role = tester_role
        self.is_legacy = is_legacy

    @discord.ui.button(label="➕ Csatlakozás / ➖ Kilépés", style=discord.ButtonStyle.blurple, custom_id="queue_join_leave_toggle")
    async def join_leave_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user

        if is_banned_by_role(user):
            return await interaction.followup.send("❌ Ki vagy tiltva a tesztekről!", ephemeral=True)

        mc_name = await get_linked_minecraft_name_async(user.id)
        if not mc_name:
            return await interaction.followup.send("❌ Először linkelned kell a Minecraft fiókodat az `/link` paranccsal!", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.followup.send("❌ Ez a várólista már nem aktív.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        existing_player = next((p for p in q_data["players"] if p["id"] == user.id), None)

        if existing_player:
            q_data["players"] = [p for p in q_data["players"] if p["id"] != user.id]
            await update_queue_message(interaction.message, q_data, self.mode_key)
            await interaction.followup.send("✅ Sikeresen kiléptél a várólistáról.", ephemeral=True)
        else:
            has_cd, cd_str = check_timeout(user.id, self.mode_key)
            if has_cd:
                return await interaction.followup.send(f"⏱️ Cooldown alatt állsz ebben a játékmódban! Még hátralévő idő: `{cd_str}`", ephemeral=True)

            if len(q_data["players"]) >= 20:
                return await interaction.followup.send("❌ A várólista tele van (20/20).", ephemeral=True)

            q_data["players"].append({
                "id": user.id,
                "mc": mc_name,
                "status": "⏳ VÁR"
            })

            await update_queue_message(interaction.message, q_data, self.mode_key)
            await interaction.followup.send(f"✅ Sikeresen csatlakoztál a(z) **{get_gamemode_display_name(self.mode_key)}** várólistához!", ephemeral=True)

    @discord.ui.button(label="➡️ Következő", style=discord.ButtonStyle.green, custom_id="queue_next")
    async def next_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff and (self.tester_role and self.tester_role not in interaction.user.roles):
            return await interaction.response.send_message("❌ Csak teszterek vagy adminok hívhatják a következő játékost!", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.response.send_message("❌ Nem található aktív sor ebben a csatornában.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        if not q_data["players"]:
            return await interaction.response.send_message("❌ Nincs játékos a várólistán!", ephemeral=True)

        target_player = q_data["players"][0]
        guild = interaction.guild
        category = get_queue_category(guild, self.is_legacy)

        player_user = guild.get_member(target_player["id"]) or await guild.fetch_member(target_player["id"])
        regulator_role = guild.get_role(REGULATOR_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            player_user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        if regulator_role:
            overwrites[regulator_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        if self.tester_role:
            overwrites[self.tester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        label = get_gamemode_display_name(self.mode_key)
        try:
            test_chan = await guild.create_text_channel(
                name=f"test-{target_player['mc'].lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"Teszt szoba - {label} | Játékos: {target_player['mc']}"
            )
        except Exception as e:
            return await interaction.response.send_message(f"❌ Nem sikerült teszt csatornát létrehozni: `{e}`", ephemeral=True)

        embed = discord.Embed(
            title=f"⚔️ Teszt Szoba: {label}",
            description=f"Játékos: <@{target_player['id']}> (**{target_player['mc']}**)\nTeszter: {interaction.user.mention}\n\nKattints az alábbi gombra az eredmény rögzítéséhez!",
            color=discord.Color.blue()
        )
        await test_chan.send(content=f"{player_user.mention} {interaction.user.mention}", embed=embed, view=TestTicketView(target_player['id'], target_player['mc'], self.mode_key, ch_id))
        await interaction.response.send_message(f"✅ Következő játékos behívva! Teszt csatorna: {test_chan.mention}", ephemeral=True)

    @discord.ui.button(label="🔒 Lezárás", style=discord.ButtonStyle.gray, custom_id="queue_close")
    async def close_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff and (self.tester_role and self.tester_role not in interaction.user.roles):
            return await interaction.response.send_message("❌ Csak teszterek vagy adminok zárhatják le a sort!", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id in ACTIVE_QUEUES:
            del ACTIVE_QUEUES[ch_id]

        await interaction.response.send_message("🔒 Várólista lezárva. A csatorna 5 másodperc múlva törlődik...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Várólista lezárva: {interaction.user.display_name}")
        except Exception:
            pass


class PanelSelectView(discord.ui.View):
    def __init__(self, mode_type: str, action_type: str):
        super().__init__(timeout=None)
        self.mode_type = mode_type
        self.action_type = action_type
        
        types_list = LEGACY_TICKET_TYPES if mode_type.lower() == "legacy" else TICKET_TYPES
        
        options = []
        for lbl, key, emoji in types_list[:25]:
            emoji_str = str(emoji)
            if emoji_str.isdigit():
                emoji_str = f"<:{lbl.replace(' ', '')}:{emoji_str}>"
            try:
                options.append(discord.SelectOption(label=lbl, value=key, emoji=emoji_str if len(emoji_str) <= 20 else None))
            except Exception:
                options.append(discord.SelectOption(label=lbl, value=key))

        if options:
            self.add_item(PanelSelect(options, mode_type, action_type))


class PanelSelect(discord.ui.Select):
    def __init__(self, options, mode_type: str, action_type: str):
        placeholders = {
            "ping": f"Válassz értesítési kategóriát ({mode_type.upper()})...",
            "queue": f"Válassz játékmódot a várólistához ({mode_type.upper()})...",
            "hightest": f"Válassz High Tier tesztet ({mode_type.upper()})..."
        }
        super().__init__(
            placeholder=placeholders.get(action_type, "Válassz..."),
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"panel_{action_type}_{mode_type.lower()}"
        )
        self.action_type = action_type
        self.mode_type = mode_type

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        label = get_gamemode_display_name(key)
        is_legacy = (self.mode_type.lower() == "legacy")
        guild = interaction.guild
        user = interaction.user

        # 1. PING PANEL
        if self.action_type == "ping":
            role_name = f"{label} Queue"
            role = discord.utils.get(guild.roles, name=role_name) or discord.utils.get(guild.roles, name=label)
            
            if not role:
                return await interaction.response.send_message(f"❌ A(z) `{role_name}` rang nem található a szerveren!", ephemeral=True)

            if role in user.roles:
                await user.remove_roles(role, reason="Ping panel - feliratkozás törlése")
                await interaction.response.send_message(f"❌ Sikeresen **leiratkoztál** erről a pingről: **{label}** ({self.mode_type})", ephemeral=True)
            else:
                await user.add_roles(role, reason="Ping panel - feliratkozás")
                await interaction.response.send_message(f"✅ Sikeresen **feliratkoztál** ehhez a pinghez: **{label}** ({self.mode_type})", ephemeral=True)
            return

        # 2. HIGHTEST PANEL (Privát High Test Ticket)
        if self.action_type == "hightest":
            if is_banned_by_role(user):
                return await interaction.response.send_message("❌ Ki vagy tiltva a tesztekről!", ephemeral=True)

            mc_name = await get_linked_minecraft_name_async(user.id)
            if not mc_name:
                return await interaction.response.send_message("❌ Először linkelned kell a Minecraft fiókodat az `/link` paranccsal!", ephemeral=True)

            await interaction.response.defer(ephemeral=True)
            category = get_ticket_category(guild, is_legacy)

            tester_role_name = f"{label} Tester"
            tester_role = discord.utils.get(guild.roles, name=tester_role_name)
            regulator_role = guild.get_role(REGULATOR_ROLE_ID)

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            }
            if tester_role:
                overwrites[tester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            if regulator_role:
                overwrites[regulator_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            try:
                ticket_chan = await guild.create_text_channel(
                    name=f"hightest-{mc_name.lower()}",
                    category=category,
                    overwrites=overwrites,
                    topic=f"High Test Ticket - {label} ({self.mode_type}) | Játékos: {mc_name}"
                )
            except Exception as e:
                return await interaction.followup.send(f"❌ Nem sikerült High Test csatornát létrehozni: `{e}`", ephemeral=True)

            embed = discord.Embed(
                title=f"⚔️ High Tier Teszt Ticket: {label} ({self.mode_type})",
                description=f"Játékos: {user.mention} (**{mc_name}**)\n\nEz egy privát High Test ticket. Kérlek várj, amíg egy teszter csatlakozik!",
                color=discord.Color.purple()
            )
            await ticket_chan.send(content=f"{user.mention}", embed=embed, view=TestTicketView(user.id, mc_name, key, None))
            return await interaction.followup.send(f"✅ High Test ticket sikeresen megnyitva: {ticket_chan.mention}", ephemeral=True)

        # 3. QUEUE PANEL (Nyilvános várólista)
        await interaction.response.defer(ephemeral=True)
        category = get_queue_category(guild, is_legacy)
        
        tester_role_name = f"{label} Tester"
        tester_role = discord.utils.get(guild.roles, name=tester_role_name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if tester_role:
            overwrites[tester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            queue_chan = await guild.create_text_channel(
                name=f"queue-{key.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"NeonTiers Várólista - {label} ({self.mode_type})"
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Nem sikerült csatornát létrehozni: `{e}`", ephemeral=True)

        queue_role = discord.utils.get(guild.roles, name=f"{label} Queue")
        q_ping = queue_role.mention if queue_role else f"@{label} Queue"

        ACTIVE_QUEUES[queue_chan.id] = {
            "players": [], 
            "testers": [user.id], 
            "gamemode": key,
            "msg_id": None
        }

        emoji_str = "🎮"
        for l, k, e in ALL_TICKET_TYPES:
            if k == key:
                emoji_str = str(e)
                break

        desc = f"**Helyek:** 0/20\n\n**Játékosok a várólistán:**\n*- Üres -*\n\n**Aktív Teszterek:**\n🛡️ <@{user.id}>\n"
        embed = discord.Embed(
            title=f"{emoji_str} {label} Várólista ({self.mode_type})", 
            description=desc, 
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        
        msg = await queue_chan.send(content=f"🔔 {q_ping}", embed=embed, view=QueueActiveView(key, tester_role, is_legacy))
        ACTIVE_QUEUES[queue_chan.id]["msg_id"] = msg.id
        await interaction.followup.send(f"✅ Várólista csatorna sikeresen megnyitva: {queue_chan.mention}", ephemeral=True)
