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

from tier_utils import (
    THEME_LIGHT_PURPLE, THEME_LIGHT_BLUE,
    HT_TICKETS_FILE, ACTIVE_QUEUES, VALID_HT_TIERS, ALLOWED_QUEUE_TIERS,
    save_test_result_supabase, get_cooldown, set_cooldown,
    check_timeout, get_ticket_category, update_queue_message
)

# =========================================
# TESZT EREDMÉNY RÖGZÍTŐ RENDSZER (MODAL)
# =========================================
class TierResultModal(discord.ui.Modal, title="Teszt Eredmény Rögzítése"):
    def __init__(self, player_id: int, player_mc: str, gamemode: str, tester_id: int, queue_ch_id: int = None):
        super().__init__()
        self.player_id = player_id
        self.player_mc = player_mc
        self.gamemode = gamemode
        self.tester_id = tester_id
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

        await save_test_result_supabase(player_user, self.player_mc, self.gamemode, tier, tester_user, interaction)
        set_cooldown(self.player_id, self.gamemode, time.time())

        # Ha várólistáról jött, eltávolítjuk a játékost a sorból
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


# =========================================
# VÁRÓLISTA AKTÍV NÉZET (Gombokkal)
# =========================================
class QueueActiveView(discord.ui.View):
    def __init__(self, mode_key: str, tester_role: discord.Role):
        super().__init__(timeout=None)
        self.mode_key = mode_key
        self.tester_role = tester_role

    @discord.ui.button(label="➕ Csatlakozás a Várólistához", style=discord.ButtonStyle.green, custom_id="queue_join")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user

        if is_banned_by_role(user):
            return await interaction.followup.send("❌ Ki vagy tiltva a tesztekről!", ephemeral=True)

        mc_name = await get_linked_minecraft_name_async(user.id)
        if not mc_name:
            return await interaction.followup.send("❌ Először linkelned kell a Minecraft fiókodat az `/link` paranccsal!", ephemeral=True)

        has_cd, cd_str = check_timeout(user.id, self.mode_key)
        if has_cd:
            return await interaction.followup.send(f"⏱️ Cooldown alatt állsz ebben a játékmódban! Még hátralévő idő: `{cd_str}`", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.followup.send("❌ Ez a várólista már nem aktív.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        if any(p["id"] == user.id for p in q_data["players"]):
            return await interaction.followup.send("⚠️ Már rajta vagy ezen a várólistán!", ephemeral=True)

        if len(q_data["players"]) >= 20:
            return await interaction.followup.send("❌ A várólista tele van (20/20).", ephemeral=True)

        q_data["players"].append({
            "id": user.id,
            "mc": mc_name,
            "status": "VÁR"
        })

        await update_queue_message(interaction.message, q_data, self.mode_key)
        await interaction.followup.send(f"✅ Sikeresen csatlakoztál a(z) **{get_gamemode_display_name(self.mode_key)}** várólistához!", ephemeral=True)

    @discord.ui.button(label="➖ Kilépés", style=discord.ButtonStyle.red, custom_id="queue_leave")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.followup.send("❌ Hiba: nem található aktív várólista.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        before_len = len(q_data["players"])
        q_data["players"] = [p for p in q_data["players"] if p["id"] != interaction.user.id]

        if len(q_data["players"]) == before_len:
            return await interaction.followup.send("⚠️ Nem is voltál rajta a várólistán.", ephemeral=True)

        await update_queue_message(interaction.message, q_data, self.mode_key)
        await interaction.followup.send("✅ Sikeresen kiléptél a várólistáról.", ephemeral=True)

    @discord.ui.button(label="🛡️ Teszt Rögzítése", style=discord.ButtonStyle.blurple, custom_id="queue_record")
    async def record_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = interaction.user.guild_permissions.administrator or any(r.id in [STAFF_ROLE_ID, REGULATOR_ROLE_ID] for r in interaction.user.roles)
        if not is_staff and (self.tester_role and self.tester_role not in interaction.user.roles):
            return await interaction.response.send_message("❌ Csak teszterek rögzíthetnek eredményt!", ephemeral=True)

        ch_id = interaction.channel.id
        if ch_id not in ACTIVE_QUEUES:
            return await interaction.response.send_message("❌ Nem található aktív sor ebben a csatornában.", ephemeral=True)

        q_data = ACTIVE_QUEUES[ch_id]
        if not q_data["players"]:
            return await interaction.response.send_message("❌ Nincs játékos a várólistán!", ephemeral=True)

        target_player = q_data["players"][0]
        modal = TierResultModal(
            player_id=target_player["id"],
            player_mc=target_player["mc"],
            gamemode=self.mode_key,
            tester_id=interaction.user.id,
            queue_ch_id=ch_id
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔒 Várólista Lezárása", style=discord.ButtonStyle.gray, custom_id="queue_close")
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
