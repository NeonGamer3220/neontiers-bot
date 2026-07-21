import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
import time

from config import STAFF_ROLE_ID, HELP_TICKET_CATEGORY_ID
from commands.staff import is_staff_member

# Ugyanaz a fájl, amit a tier_system.py HT/queue ticketjei is használnak,
# így az automatikus 44h/48h inaktivitás-figyelő rendszer ezekre is vonatkozik.
HT_TICKETS_FILE = "ht_tickets.json"
PANEL_COLOR = 0xB026FF  # Élénk neon lila

# ==========================================
# SEGÉDFÜGGVÉNYEK (JSON TÁROLÁS)
# ==========================================
def _load_tickets() -> dict:
    if not os.path.exists(HT_TICKETS_FILE):
        return {}
    try:
        with open(HT_TICKETS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_tickets(data: dict):
    with open(HT_TICKETS_FILE, "w") as f:
        json.dump(data, f)

def user_has_open_help_ticket(guild: discord.Guild, user_id: int) -> bool:
    data = _load_tickets()
    for ch_id_str, info in data.items():
        if info.get("type") == "help" and info.get("owner_id") == user_id:
            if guild.get_channel(int(ch_id_str)):
                return True
    return False

def _mention_or_fallback(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.mention if member else f"<@{user_id}>"

def build_ticket_embed(guild: discord.Guild, owner_id: int, claimer_id: int = None) -> discord.Embed:
    if claimer_id:
        claim_text = _mention_or_fallback(guild, claimer_id)
    else:
        claim_text = "*Senki - kattints az Átvétel gombra!*"

    embed = discord.Embed(
        title="🎫 Segítségkérésed",
        description=(
            f"Neked nyitva: {_mention_or_fallback(guild, owner_id)}\n\n"
            f"**Átvette**\n{claim_text}\n\n"
            f"**Inaktivitás**\n"
            f"Bármilyen emberi üzenet újraindítja a 48 órás számlálót. Automatikus zárás előtt 4 órával figyelmeztetést küldök.\n\n"
            f"Ha végeztetek, a kérelmet staff zárhatja le, utána a csatorna törlődik."
        ),
        color=PANEL_COLOR,
        timestamp=discord.utils.utcnow()
    )
    return embed

# ==========================================
# TICKET VEZÉRLŐ GOMBOK (BENT A TICKETBEN)
# ==========================================
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Átvétel / Leadás", style=discord.ButtonStyle.primary, custom_id="help_ticket_claim", emoji="🙋")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Csak staff tagok vehetik át a kérelmet!", ephemeral=True)

        data = _load_tickets()
        ch_id = str(interaction.channel.id)
        info = data.get(ch_id)
        if not info:
            return await interaction.response.send_message("❌ Ez nem egy regisztrált ticket.", ephemeral=True)

        owner_id = info.get("owner_id")
        current_claimer = info.get("claimer_id")

        if current_claimer == interaction.user.id:
            info["claimer_id"] = None
            data[ch_id] = info
            _save_tickets(data)
            embed = build_ticket_embed(interaction.guild, owner_id, None)
            await interaction.response.edit_message(embed=embed)
            await interaction.channel.send(f"↩️ {interaction.user.mention} leadta a kérelmet.")
        elif current_claimer:
            name = _mention_or_fallback(interaction.guild, current_claimer)
            return await interaction.response.send_message(f"❌ Ezt már átvette {name}!", ephemeral=True)
        else:
            info["claimer_id"] = interaction.user.id
            data[ch_id] = info
            _save_tickets(data)
            embed = build_ticket_embed(interaction.guild, owner_id, interaction.user.id)
            await interaction.response.edit_message(embed=embed)
            await interaction.channel.send(f"✅ {interaction.user.mention} átvette a kérelmet.")

    @discord.ui.button(label="Lezárás", style=discord.ButtonStyle.danger, custom_id="help_ticket_close", emoji="🔒")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Csak staff zárhatja le a kérelmet!", ephemeral=True)

        await interaction.response.send_message("🔒 Ticket zárása 5 másodperc múlva...")

        data = _load_tickets()
        ch_id = str(interaction.channel.id)
        if ch_id in data:
            del data[ch_id]
            _save_tickets(data)

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

# ==========================================
# PANEL GOMB (MEGNYITÁS)
# ==========================================
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Megnyitás", style=discord.ButtonStyle.success, custom_id="help_ticket_open", emoji="🟢")
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        if user_has_open_help_ticket(guild, user.id):
            return await interaction.followup.send("❌ Már van egy nyitott segítségkérésed! Egyszerre csak egy lehet nyitva.", ephemeral=True)

        category = guild.get_channel(HELP_TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("❌ Nem található a ticket kategória. Szólj egy adminnak!", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
        }
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)

        safe_name = "".join(c for c in user.name.lower() if c.isalnum())[:20] or "user"

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}", category=category, overwrites=overwrites
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Hiba a csatorna létrehozásakor: {e}", ephemeral=True)

        embed = build_ticket_embed(guild, user.id, None)
        await channel.send(content=user.mention, embed=embed, view=TicketControlView())

        data = _load_tickets()
        data[str(channel.id)] = {
            "owner_id": user.id,
            "claimer_id": None,
            "last_msg_time": time.time(),
            "warned": False,
            "forcekeep": False,
            "type": "help"
        }
        _save_tickets(data)

        await interaction.followup.send(f"✅ Segítségkérés létrehozva: {channel.mention}", ephemeral=True)

# ==========================================
# COG ÉS SLASH PARANCS
# ==========================================
class TicketPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketpanel", description="Lerakja a NeonTiers segítségkérés (support) ticket panelt. (Admin)")
    async def ticketpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)

        embed = discord.Embed(
            title="🎫 NeonTiers Ticket",
            description=(
                "Ha segítség kell, nyiss kérelmet. Sima segítségkéréshez nem kell Minecraft nevet megadnod.\n\n"
                "**Fontos**\n"
                "Egyszerre egy nyitott segítségkérésed lehet.\n\n"
                "**Automatikus lezárás**\n"
                "Bármilyen emberi üzenet újraindítja a 48 órás inaktivitási számlálót. Automatikus zárás előtt 4 órával figyelmeztetést küldök és megpingelem a nyitót."
            ),
            color=PANEL_COLOR
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message("✅ Panel lerakva!", ephemeral=True)

async def setup(bot):
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    await bot.add_cog(TicketPanelCog(bot))
