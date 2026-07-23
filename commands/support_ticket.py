import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import time
import asyncio

from config import STAFF_ROLE_ID, HELP_TICKET_CATEGORY_ID

HT_TICKETS_FILE = "ht_tickets.json"
PANEL_COLOR = 0xB026FF

def _load_tickets() -> dict:
    if not os.path.exists(HT_TICKETS_FILE):
        return {}
    try:
        with open(HT_TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_tickets(data: dict):
    try:
        with open(HT_TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[TICKET SAVE ERROR] {e}")

def user_has_open_help_ticket(guild: discord.Guild, user_id: int) -> bool:
    data = _load_tickets()
    for ch_id_str, info in data.items():
        if info.get("type") == "help" and info.get("owner_id") == user_id:
            if guild.get_channel(int(ch_id_str)):
                return True
    return False

class SupportTicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Ticket Lezárása", style=discord.ButtonStyle.danger, custom_id="close_support_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        ch = interaction.channel
        data = _load_tickets()
        ch_id_str = str(ch.id)
        
        if ch_id_str in data:
            del data[ch_id_str]
            _save_tickets(data)

        await ch.send("🔒 A ticket 5 másodperc múlva törlődik...")
        await asyncio.sleep(5)
        try:
            await ch.delete()
        except Exception:
            pass

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Segítségkérés Nyitása", style=discord.ButtonStyle.primary, custom_id="open_support_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        if user_has_open_help_ticket(guild, interaction.user.id):
            return await interaction.followup.send("❌ Már van egy nyitott segítségkérő ticketed!", ephemeral=True)

        category = guild.get_channel(HELP_TICKET_CATEGORY_ID) if HELP_TICKET_CATEGORY_ID else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ch_name = f"help-{interaction.user.name}".lower()[:99]
        channel = await guild.create_text_channel(name=ch_name, category=category, overwrites=overwrites)

        data = _load_tickets()
        data[str(channel.id)] = {
            "owner_id": interaction.user.id,
            "type": "help",
            "last_msg_time": time.time(),
            "warned": False,
            "forcekeep": False
        }
        _save_tickets(data)

        embed = discord.Embed(
            title="🎫 NeonTiers | Segítségkérés",
            description=f"Üdv {interaction.user.mention}!\n\nKérjük, írd le részletesen, miben tudunk segíteni. A Staff csapat hamarosan válaszol.",
            color=PANEL_COLOR
        )
        await channel.send(content=f"{interaction.user.mention} {staff_role.mention if staff_role else ''}", embed=embed, view=SupportTicketCloseView())
        await interaction.followup.send(f"✅ Segítségkérés létrehozva: {channel.mention}", ephemeral=True)

class TicketPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketpanel", description="Lerakja a NeonTiers segítségkérés ticket panelt. (Admin)")
    async def ticketpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)

        embed = discord.Embed(
            title="🎫 NeonTiers Ticket",
            description=(
                "Ha segítség kell, nyiss kérelmet.\n\n"
                "**Fontos**\nEgyszerre egy nyitott segítségkérésed lehet.\n\n"
                "**Automatikus lezárás**\n48 óra inaktivitás után a ticket automatikusan lezárul."
            ),
            color=PANEL_COLOR
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message("✅ Panel lerakva!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketPanelCog(bot))
