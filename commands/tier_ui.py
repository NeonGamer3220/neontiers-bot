"""
NeonTiers Bot - Tier UI & Modals (commands/tier_ui.py)
High Test javaslat beküldő modal (nem zárja be azonnal a csatornát) és tier alapú High Test opciók.
"""

import discord
import asyncio
import time
from config import TICKET_TYPES, LEGACY_TICKET_TYPES, ALL_TICKET_TYPES, get_gamemode_display_name, STAFF_ROLE_ID, REGULATOR_ROLE_ID, RANKS, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID, LOG_CHANNEL_ID, TIER_GIVER_ROLE_ID, TESTER_ROLE_ID
from commands.tier_utils import (
    ACTIVE_QUEUES, INACTIVE_TICKETS, VALID_HT_TIERS, ALLOWED_QUEUE_TIERS,
    get_ticket_category, get_queue_category, update_queue_message, 
    set_cooldown, check_timeout, THEME_LIGHT_PURPLE, archive_channel,
    is_dm_optout, set_dm_optout
)
from commands.ban_enforcement import is_banned_by_role
from database import get_linked_minecraft_name_async, save_test_result_supabase, get_player_rank_async


def _find_gamemode_tester_role(guild: discord.Guild, gamemode_label: str):
    """Megkeresi a játékmód-specifikus Tester rangot a szerveren, mind a
    "{label} Tester", mind a "{label} Teszter" (magyar) elnevezéssel."""
    for suffix in ("Tester", "Teszter"):
        role = discord.utils.get(guild.roles, name=f"{gamemode_label} {suffix}")
        if role:
            return role
    return None


def _can_give_tiers(member: discord.Member) -> bool:
    """Csak a TIER_GIVER_ROLE_ID rang (vagy admin) hívhatja a 'Következő' gombot
    és adhat/rögzíthet tiert."""
    if member.guild_permissions.administrator:
        return True
    return any(r.id == TIER_GIVER_ROLE_ID for r in member.roles)


def _can_open_queue(member: discord.Member, guild: discord.Guild, gamemode_label: str):
    """Eldönti, hogy a tag megnyithatja-e egy adott játékmód várólistáját.

    - Admin / Staff / Regulátor mindig megnyithatja.
    - Egyébként a tagnak rendelkeznie kell az általános TESTER_ROLE_ID
      ("Tester") ranggal, ÉS - ha az adott játékmódhoz létezik ilyen nevű
      rang a szerveren - a "{gamemode_label} Tester" (pl. "DiaSMP Tester")
      játékmód-specifikus ranggal is. Ha valakinek csak az általános Tester
      rangja van meg, de a konkrét játékmódhoz tartozó nincs, nem nyithat
      várólistát abban a módban.

    Visszatérési érték: (engedélyezve: bool, hibaüzenet: str | None)
    """
    if member.guild_permissions.administrator:
        return True, None

    role_ids = {r.id for r in member.roles}
    if role_ids & {STAFF_ROLE_ID, REGULATOR_ROLE_ID}:
        return True, None

    general_tester_role = guild.get_role(TESTER_ROLE_ID)
    if not general_tester_role or general_tester_role not in member.roles:
        return False, "❌ Nincs jogosultságod várólistát nyitni: szükséged van a **Tester** rangra."

    gamemode_role = _find_gamemode_tester_role(guild, gamemode_label)
    if not gamemode_role or gamemode_role not in member.roles:
        return False, f"❌ Nincs jogosultságod ehhez a játékmódhoz: hiányzik a **{gamemode_label} Tester** rangod."

    return True, None


class HighTestNoteModal(discord.ui.Modal, title="Megjegyzés Beküldése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode

        self.note_input = discord.ui.TextInput(
            label="Megjegyzés / Vélemény",
            placeholder="Írd le a javaslatodat vagy a teszt részleteit...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1500
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        note_text = self.note_input.value.strip()
        user = interaction.user

        embed = discord.Embed(
            title=f"💬 Megjegyzés érkezett ({get_gamemode_display_name(self.gamemode)})",
            description=note_text,
            color=discord.Color.gold()
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url if user.display_avatar else None)
        embed.add_field(name="Érintett Játékos", value=f"<@{self.player_id}> (**{self.player_mc}**)", inline=False)
        embed.set_footer(text="NeonTiers Management System")

        if interaction.channel.id in INACTIVE_TICKETS:
            INACTIVE_TICKETS[interaction.channel.id]["last_activity"] = time.time()
            INACTIVE_TICKETS[interaction.channel.id]["warned"] = False

        reg_ping = f"<@&{REGULATOR_ROLE_ID}>" if REGULATOR_ROLE_ID else ""
        await interaction.channel.send(content=reg_ping or None, embed=embed)
        await interaction.followup.send("✅ Megjegyzés sikeresen beküldve a ticketbe!", ephemeral=True)


class HighTestSuggestionModal(discord.ui.Modal, title="Tier Javaslat Beküldése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode

        self.tier_input = discord.ui.TextInput(
            label="Javasolt Tier",
            placeholder="pl. LT2, HT1",
            required=True,
            max_length=20
        )
        self.note_input = discord.ui.TextInput(
            label="Megjegyzés / Indoklás (opcionális)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        self.add_item(self.tier_input)
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tier = self.tier_input.value.strip().upper()
        if tier not in VALID_HT_TIERS and tier != "UNRANKED":
            return await interaction.followup.send(f"❌ Érvénytelen tier formátum: `{tier}`. Használhatók: HT1-LT5, Unranked", ephemeral=True)

        note_text = self.note_input.value.strip()
        user = interaction.user

        embed = discord.Embed(
            title=f"📊 Tier Javaslat ({get_gamemode_display_name(self.gamemode)})",
            color=discord.Color.purple()
        )
        embed.add_field(name="Játékos", value=f"<@{self.player_id}> (**{self.player_mc}**)", inline=False)
        embed.add_field(name="Javasolt Tier", value=f"**{tier}**", inline=True)
        if note_text:
            embed.add_field(name="Megjegyzés", value=note_text, inline=False)
        embed.set_footer(text=f"Javasolta: {user.display_name} | Ellenőrzésre vár egy Regulátortól")

        if interaction.channel.id in INACTIVE_TICKETS:
            INACTIVE_TICKETS[interaction.channel.id]["last_activity"] = time.time()
            INACTIVE_TICKETS[interaction.channel.id]["warned"] = False

        reg_ping = f"<@&{REGULATOR_ROLE_ID}>" if REGULATOR_ROLE_ID else ""
        await interaction.channel.send(content=(reg_ping or None), embed=embed)
        await interaction.followup.send("✅ Tier javaslat beküldve! Egy Regulátornak ellenőriznie és a tierlist weboldalán rögzítenie kell.", ephemeral=True)


class HighTestTicketView(discord.ui.View):
    def __init__(self, player_id: int, player_mc: str, gamemode: str):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode

    @discord.ui.button(label="📝 Tier Javaslat", style=discord.ButtonStyle.green, custom_id="hightest_suggest_btn")
    async def suggest_tier(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = HighTestSuggestionModal(
            player_id=self.player_id,
            player_mc=self.player_mc,
            gamemode=self.gamemode
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔒 Lezárás", style=discord.ButtonStyle.gray, custom_id="hightest_close_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff and interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ Ezt a ticketet csak a játékos vagy staff zárhatja le!", ephemeral=True)

        if interaction.channel.id in INACTIVE_TICKETS:
            del INACTIVE_TICKETS[interaction.channel.id]

        await interaction.response.send_message("🔒 Ticket lezárva. A csatorna 3 másodperc múlva törlődik...", ephemeral=True)
        await archive_channel(interaction.channel, interaction.user, reason="High Test lezárva eredmény nélkül")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"High Test lezárva: {interaction.user.display_name}")
        except Exception:
            pass


class TestFeedbackModal(discord.ui.Modal, title="Teszt Értékelése"):
    def __init__(self, player_id: int, gamemode_label: str):
        super().__init__()
        self.player_id = player_id
        self.gamemode_label = gamemode_label

        self.feedback_input = discord.ui.TextInput(
            label="Véleményed a tesztről",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.feedback_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        log_chan = interaction.client.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None
        embed = discord.Embed(
            title=f"⭐ Teszt Értékelés ({self.gamemode_label})",
            description=self.feedback_input.value.strip(),
            color=discord.Color.gold()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
        embed.set_footer(text=f"Discord ID: {interaction.user.id}")
        if log_chan:
            try:
                await log_chan.send(embed=embed)
            except Exception:
                pass
        await interaction.followup.send("✅ Köszönjük az értékelést!", ephemeral=True)


class TestFeedbackView(discord.ui.View):
    def __init__(self, player_id: int, gamemode_label: str):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.gamemode_label = gamemode_label

    @discord.ui.button(label="⭐ Értékelés", style=discord.ButtonStyle.blurple, custom_id="dm_feedback_btn")
    async def give_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ Ez nem a te értesítésed!", ephemeral=True)
        await interaction.response.send_modal(TestFeedbackModal(self.player_id, self.gamemode_label))

    @discord.ui.button(label="🔕 Ne küldj több ilyen üzenetet", style=discord.ButtonStyle.gray, custom_id="dm_optout_btn")
    async def opt_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ Ez nem a te értesítésed!", ephemeral=True)
        set_dm_optout(interaction.user.id)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🔕 Rendben, mostantól nem küldünk több ilyen privát üzenetet!", ephemeral=True)


class TestResultModal(discord.ui.Modal, title="Teszt Eredmény Rögzítése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, queue_ch_id: int = None, is_legacy: bool = False):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.queue_ch_id = queue_ch_id
        self.is_legacy = is_legacy

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
        if tier not in ALLOWED_QUEUE_TIERS:
            return await interaction.followup.send(
                "❌ Várólista tesztből **maximum LT3** adható. Ha ennél magasabb szintet ért el a játékos, nyiss neki egy **High Test** kérelmet a megfelelő módban!",
                ephemeral=True
            )

        guild = interaction.guild
        player_user = guild.get_member(self.player_id) or await guild.fetch_member(self.player_id)
        tester_user = interaction.user
        label = get_gamemode_display_name(self.gamemode)

        try:
            await save_test_result_supabase(player_user, self.player_mc, label, tier, tester_user, interaction)
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

        # Eredmény közzététele a megfelelő (Modern/Legacy) eredmény csatornában
        results_chan_id = LEGACY_RESULT_CHANNEL_ID if self.is_legacy else MODERN_RESULT_CHANNEL_ID
        results_chan = guild.get_channel(results_chan_id) if results_chan_id else None
        if results_chan:
            result_embed = discord.Embed(
                title=f"📋 Teszt Eredmény - {label}",
                description=f"Játékos: <@{self.player_id}> (**{self.player_mc}**)\nEredmény: **{tier}**\nTeszter: {tester_user.mention}",
                color=discord.Color.green()
            )
            try:
                await results_chan.send(embed=result_embed)
            except Exception:
                pass

        # DM a játékosnak, ha nem tiltotta le az értesítéseket
        if not is_dm_optout(self.player_id):
            try:
                dm_embed = discord.Embed(
                    title="📋 Teszt Eredmény",
                    description=f"A(z) **{label}** tesztedet **{tester_user.display_name}** rögzítette.\nEredmény: **{tier}**",
                    color=discord.Color.green()
                )
                await player_user.send(embed=dm_embed, view=TestFeedbackView(self.player_id, label))
            except Exception:
                pass

        await archive_channel(interaction.channel, tester_user, reason=f"Teszt eredmény rögzítve: {tier}")

        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Teszt befejezve: {tester_user.display_name}")
        except Exception:
            pass


class TestTicketView(discord.ui.View):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, queue_ch_id: int = None, is_legacy: bool = False):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.queue_ch_id = queue_ch_id
        self.is_legacy = is_legacy

    @discord.ui.button(label="📝 Eredmény Rögzítése", style=discord.ButtonStyle.green, custom_id="test_record_result")
    async def record_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _can_give_tiers(interaction.user):
            return await interaction.response.send_message("❌ Csak a jogosult rang adhat/rögzíthet tiert!", ephemeral=True)

        modal = TestResultModal(
            player_id=self.player_id,
            player_mc=self.player_mc,
            gamemode=self.gamemode,
            queue_ch_id=self.queue_ch_id,
            is_legacy=self.is_legacy
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔒 Ticket lezárása", style=discord.ButtonStyle.danger, custom_id="test_close_no_result")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff:
            return await interaction.response.send_message("❌ Csak teszterek vagy regulatorok zárhatják le a ticketet!", ephemeral=True)

        await interaction.response.send_message("🔒 Ticket lezárása 5 másodperc múlva...")

        if self.queue_ch_id and self.queue_ch_id in ACTIVE_QUEUES:
            q_data = ACTIVE_QUEUES[self.queue_ch_id]
            q_data["players"] = [p for p in q_data["players"] if p["id"] != self.player_id]
            try:
                chan = interaction.guild.get_channel(self.queue_ch_id)
                if chan and q_data.get("msg_id"):
                    msg = await chan.fetch_message(q_data["msg_id"])
                    await update_queue_message(msg, q_data, self.gamemode)
            except Exception:
                pass

        await asyncio.sleep(5)
        await archive_channel(interaction.channel, interaction.user, reason="Teszt lezárva eredmény nélkül")
        try:
            await interaction.channel.delete(reason=f"Teszt lezárva eredmény nélkül: {interaction.user.display_name}")
        except Exception:
            pass


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
        if not _can_give_tiers(interaction.user):
            return await interaction.response.send_message("❌ Csak a jogosult rang hívhatja a következő játékost!", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.response.send_message("❌ Nem található aktív sor ebben a csatornában.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        if not q_data["players"]:
            return await interaction.response.send_message("❌ Nincs játékos a várólistán!", ephemeral=True)

        target_player = next((p for p in q_data["players"] if p["status"] == "⏳ VÁR"), None)
        if not target_player:
            return await interaction.response.send_message("❌ Nincs olyan játékos, aki épp ne tesztelődne!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        target_player["status"] = "🧪 TESZT"
        try:
            await update_queue_message(interaction.message, q_data, self.mode_key)
        except Exception:
            pass

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
            target_player["status"] = "⏳ VÁR"
            try:
                await update_queue_message(interaction.message, q_data, self.mode_key)
            except Exception:
                pass
            return await interaction.followup.send(f"❌ Nem sikerült teszt csatornát létrehozni: `{e}`", ephemeral=True)

        embed = discord.Embed(
            title=f"⚔️ Teszt Szoba: {label}",
            description=f"Játékos: <@{target_player['id']}> (**{target_player['mc']}**)\nTeszter: {interaction.user.mention}\n\nKattints az alábbi gombra az eredmény rögzítéséhez!",
            color=discord.Color.blue()
        )
        await test_chan.send(content=f"{player_user.mention} {interaction.user.mention}", embed=embed, view=TestTicketView(target_player['id'], target_player['mc'], self.mode_key, ch_id, self.is_legacy))
        await interaction.followup.send(f"✅ Következő játékos behívva! Teszt csatorna: {test_chan.mention}", ephemeral=True)

        if not is_dm_optout(target_player['id']):
            try:
                dm_embed = discord.Embed(
                    title="🎮 Sorra kerültél!",
                    description=f"Sorra kerültél a(z) **{label}** várólistában!\nTeszt szobád: {test_chan.mention}\nTeszter: {interaction.user.display_name}",
                    color=discord.Color.blue()
                )
                await player_user.send(embed=dm_embed)
            except Exception:
                pass

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
        await archive_channel(interaction.channel, interaction.user, reason="Várólista lezárva")
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
            "hightest": f"Válassz High Tier szintet ({mode_type.upper()})..."
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
        key = self.values[0]  # pl. "HT4" vagy játékmód kulcs
        is_legacy = (self.mode_type.lower() == "legacy")
        guild = interaction.guild
        user = interaction.user

        # 1. PING PANEL
        if self.action_type == "ping":
            label = get_gamemode_display_name(key)
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

        # 2. HIGHTEST PANEL (High Test Ticket - adott játékmódban magasabb tier kérése)
        if self.action_type == "hightest":
            if is_banned_by_role(user):
                return await interaction.response.send_message("❌ Ki vagy tiltva a tesztekről!", ephemeral=True)

            mc_name = await get_linked_minecraft_name_async(user.id)
            if not mc_name:
                return await interaction.response.send_message("❌ Először linkelned kell a Minecraft fiókodat az `/link` paranccsal!", ephemeral=True)

            await interaction.response.defer(ephemeral=True)

            label = get_gamemode_display_name(key)
            current_tier = await get_player_rank_async(mc_name, label)

            def rank_index(r):
                try:
                    return RANKS.index(r)
                except ValueError:
                    return -1

            if rank_index(current_tier) < RANKS.index("LT3"):
                return await interaction.followup.send(
                    f"❌ Csak akkor nyithatsz High Test kérelmet **{label}** módban, ha legalább **LT3** ranggal rendelkezel ebben a módban! (Jelenlegi szinted: {current_tier})",
                    ephemeral=True
                )

            category = get_ticket_category(guild, is_legacy)

            tester_role = _find_gamemode_tester_role(guild, label)
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
                    name=f"hightest-{key.lower()}-{mc_name.lower()}",
                    category=category,
                    overwrites=overwrites,
                    topic=f"High Test Ticket - {label} ({self.mode_type}) | Játékos: {mc_name} | Jelenlegi szint: {current_tier}"
                )
            except Exception as e:
                return await interaction.followup.send(f"❌ Nem sikerült High Test csatornát létrehozni: `{e}`", ephemeral=True)

            INACTIVE_TICKETS[ticket_chan.id] = {
                "owner_id": user.id,
                "warned": False,
                "last_activity": time.time()
            }

            reg_ping = f"<@&{REGULATOR_ROLE_ID}>" if regulator_role else ""
            embed = discord.Embed(
                title=f"⚔️ High Tier Teszt: {label} ({self.mode_type})",
                description=(
                    f"Játékos: {user.mention} (**{mc_name}**)\n"
                    f"Jelenlegi szint ebben a módban: **{current_tier}**\n\n"
                    f"Ez egy privát High Test ticket. A teszter/regulator itt rögzítheti az eredményt.\n\n"
                    f"**Inaktivitás**\nBármilyen emberi üzenet újraindítja a 48 órás számlálót. Automatikus zárás előtt 4 órával figyelmeztetés érkezik."
                ),
                color=discord.Color.purple()
            )
            await ticket_chan.send(content=f"{user.mention} {reg_ping}".strip(), embed=embed, view=HighTestTicketView(user.id, mc_name, key))
            return await interaction.followup.send(f"✅ High Test ticket sikeresen megnyitva: {ticket_chan.mention}", ephemeral=True)

        # 3. QUEUE PANEL (Várólista)
        label = get_gamemode_display_name(key)

        can_open, deny_reason = _can_open_queue(user, guild, label)
        if not can_open:
            return await interaction.response.send_message(deny_reason, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        category = get_queue_category(guild, is_legacy)
        
        tester_role = _find_gamemode_tester_role(guild, label)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
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
