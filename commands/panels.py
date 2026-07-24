"""
NeonTiers Bot - Panel Parancsok (commands/panels.py)
/queuepanel, /highticketpanel és /pingpanel kezelése Modern és Legacy típusokkal.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    LEGACY_TICKET_TYPES,
    TICKET_TYPES,
    config,
)

log = logging.getLogger("neontiers.commands.panels")


# ==========================================
# 1. QUEUE MENÜK ÉS VIEWEK
# ==========================================

class QueueSelect(discord.ui.Select):
    def __init__(self, ticket_types: list, panel_type: str):
        options = [
            discord.SelectOption(
                label=display,
                value=key,
                emoji=emoji if emoji.startswith("<") or len(emoji) <= 2 else None,
                description=f"{display} queue indítása"
            )
            for display, key, emoji in ticket_types
        ]
        super().__init__(
            placeholder=f"Válassz egy {panel_type} játékmódot a Queue elindításához...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"queue_select_{panel_type.lower()}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_mode = self.values[0]
        await interaction.response.send_message(
            f"✅ A(z) **{selected_mode.upper()}** queue sikeresen elindítva!",
            ephemeral=True
        )


class QueuePanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(QueueSelect(ticket_types, panel_type))


# ==========================================
# 2. HIGH TICKET MENÜK ÉS VIEWEK
# ==========================================

class HighTicketSelect(discord.ui.Select):
    def __init__(self, ticket_types: list, panel_type: str):
        options = [
            discord.SelectOption(
                label=display,
                value=key,
                emoji=emoji if emoji.startswith("<") or len(emoji) <= 2 else None,
                description=f"Magas teszt kérése: {display}"
            )
            for display, key, emoji in ticket_types
        ]
        super().__init__(
            placeholder=f"Válassz {panel_type} játékmódot a Magas Teszthez...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"highticket_select_{panel_type.lower()}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_mode = self.values[0]
        await interaction.response.send_message(
            f"🎫 Magas teszt ticket kérelmezve a(z) **{selected_mode.upper()}** játékmódhoz!",
            ephemeral=True
        )


class HighTicketPanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(HighTicketSelect(ticket_types, panel_type))


# ==========================================
# 3. PING ROLE MENÜK ÉS VIEWEK
# ==========================================

class PingRoleSelect(discord.ui.Select):
    def __init__(self, ticket_types: list, panel_type: str):
        options = [
            discord.SelectOption(
                label=f"{display} Ping",
                value=f"ping_{key}",
                emoji=emoji if emoji.startswith("<") or len(emoji) <= 2 else None,
                description=f"Értesítések kérése/lemondása: {display}"
            )
            for display, key, emoji in ticket_types
        ]
        super().__init__(
            placeholder=f"Válaszd ki a {panel_type} Ping rangokat...",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id=f"ping_select_{panel_type.lower()}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_roles = self.values
        await interaction.response.send_message(
            f"🔔 A kiválasztott értesítési rangok frissítve lettek! ({len(selected_roles)} kiválasztva)",
            ephemeral=True
        )


class PingPanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(PingRoleSelect(ticket_types, panel_type))


# ==========================================
# COG ÉS SLASH PARANCSOK
# ==========================================

class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ----------------------------------------------------
    # /queuepanel [tipus: Modern / Legacy]
    # ----------------------------------------------------
    @app_commands.command(name="queuepanel", description="Queue indító panel kiküldése a tesztereknek.")
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction, tipus: app_commands.Choice[str]) -> None:
        is_legacy = tipus.value == "legacy"
        ticket_list = LEGACY_TICKET_TYPES if is_legacy else TICKET_TYPES
        title_prefix = "📜 Legacy" if is_legacy else "⚔️ Modern"

        embed = discord.Embed(
            title=f"{title_prefix} Tier Queue Panel",
            description=(
                "Válaszd ki a gördülőmenüből azt a játékmódot, amiből **Queue-t** szeretnél indítani.\n\n"
                "*(Csak teszterek és staff tagok számára!)*"
            ),
            color=discord.Color.gold() if is_legacy else discord.Color.blue()
        )
        embed.set_footer(text="NeonTiers.hu • Queue Rendszer")

        view = QueuePanelView(ticket_list, tipus.name)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Queue panel sikeresen kihelyezve!", ephemeral=True)

    # ----------------------------------------------------
    # /highticketpanel [tipus: Modern / Legacy]
    # ----------------------------------------------------
    @app_commands.command(name="highticketpanel", description="Magas teszt kérelem panel kiküldése.")
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def highticketpanel(self, interaction: discord.Interaction, tipus: app_commands.Choice[str]) -> None:
        is_legacy = tipus.value == "legacy"
        ticket_list = LEGACY_TICKET_TYPES if is_legacy else TICKET_TYPES
        title_prefix = "📜 Legacy" if is_legacy else "🔥 Modern"

        embed = discord.Embed(
            title=f"{title_prefix} Magas Teszt Kérelem",
            description=(
                "Ha elérési feltételekkel rendelkezel, válaszd ki a kívánt játékmódot a menüből "
                "egy **Magas Teszt Ticket** nyitásához!"
            ),
            color=discord.Color.purple() if is_legacy else discord.Color.red()
        )
        embed.set_footer(text="NeonTiers.hu • High Tier System")

        view = HighTicketPanelView(ticket_list, tipus.name)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ High Ticket panel sikeresen kihelyezve!", ephemeral=True)

    # ----------------------------------------------------
    # /pingpanel [tipus: Modern / Legacy]
    # ----------------------------------------------------
    @app_commands.command(name="pingpanel", description="Queue ping értesítési rang kérése panel.")
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def pingpanel(self, interaction: discord.Interaction, tipus: app_commands.Choice[str]) -> None:
        is_legacy = tipus.value == "legacy"
        ticket_list = LEGACY_TICKET_TYPES if is_legacy else TICKET_TYPES
        title_prefix = "📜 Legacy" if is_legacy else "🔔 Modern"

        embed = discord.Embed(
            title=f"{title_prefix} Queue Ping Rangok",
            description=(
                "Szeretnél értesítést kapni, ha elindul egy teszt queue?\n"
                "Válaszd ki a menüből a téged érdeklő játékmódokat a **Ping rangok** felvételéhez!"
            ),
            color=discord.Color.green() if is_legacy else discord.Color.teal()
        )
        embed.set_footer(text="NeonTiers.hu • Ping Rendszer")

        view = PingPanelView(ticket_list, tipus.name)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Ping panel sikeresen kihelyezve!", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelsCog(bot))
