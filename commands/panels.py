"""
NeonTiers Bot - Panel Parancsok & Dinamikus Queue Rendszer (commands/panels.py)
/queuepanel, /highticketpanel, /pingpanel és /panel setup parancsok.
"""

import asyncio
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

# Memóriában (vagy configban) tárolt dinamikus kategória beállítások
PANEL_CONFIG = {
    "queue_category_id": None,
    "log_channel_id": None,
}


# ==========================================
# QUEUE CONTROL & LEZÁRÁS (1 CSATORNÁS RENDSZER)
# ==========================================

class CloseQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🛑 Queue Bezárása & Csatorna Törlése",
        style=discord.ButtonStyle.danger,
        custom_id="close_dynamic_queue_btn"
    )
    async def close_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ellenőrzés: Admin vagy Teszter jogosultság
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Csak teszterek / staff tagok zárhatják be a queue-t!", ephemeral=True)
            return

        await interaction.response.send_message("🧹 A Queue lezárult. A csatorna **5 másodperc** múlva törlődik...")
        
        # 5 másodperc várakozás, majd csatorna törlése
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Queue lezárva {interaction.user.display_name} által.")
        except Exception as exc:
            log.error("Hiba a csatorna törlésekor: %s", exc)


# ==========================================
# SELECT MENÜK A PANELEKHEZ
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
        guild = interaction.guild

        # Megkeressük a beállított kategóriát
        category_id = PANEL_CONFIG.get("queue_category_id") or getattr(config, "QUEUE_CATEGORY_ID", None)
        category = guild.get_channel(category_id) if category_id else interaction.channel.category

        # Dinamikus 1 csatorna létrehozása az adott játékmódhoz
        channel_name = f"⚔️-{selected_mode}-queue"
        
        try:
            queue_chan = await guild.create_text_channel(
                name=channel_name,
                category=category,
                reason=f"Queue indítva: {selected_mode} ({interaction.user.display_name})"
            )

            # Értesítő embed az új csatornában
            embed = discord.Embed(
                title=f"🚀 Aktív Queue: {selected_mode.upper()}",
                description=(
                    f"A(z) **{selected_mode.upper()}** teszt queue elindult!\n\n"
                    f"• **Indította:** {interaction.user.mention}\n"
                    f"• Csatlakozz a várakozókhoz, vagy jelezd a szándékodat ebben a csatornában!\n\n"
                    "*(Ha a tesztelés véget ért, a teszter a lenti gombbal törli a csatornát.)*"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text="NeonTiers.hu • Dinamikus Queue Rendszer")

            await queue_chan.send(embed=embed, view=CloseQueueView())

            await interaction.response.send_message(
                f"✅ A queue csatorna sikeresen létrejött: {queue_chan.mention}",
                ephemeral=True
            )

        except Exception as exc:
            log.error("Hiba a dinamikus queue csatorna létrehozásakor: %s", exc)
            await interaction.response.send_message(
                f"❌ Nem sikerült létrehozni a csatornát. Ellenőrizd a bot jogosultságait! (Hiba: {exc})",
                ephemeral=True
            )


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


# ==========================================
# VIEWEK A PANELEKHEZ
# ==========================================

class QueuePanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(QueueSelect(ticket_types, panel_type))


class HighTicketPanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(HighTicketSelect(ticket_types, panel_type))


class PingPanelView(discord.ui.View):
    def __init__(self, ticket_types: list, panel_type: str):
        super().__init__(timeout=None)
        self.add_item(PingRoleSelect(ticket_types, panel_type))


# ==========================================
# COG ÉS PARANCSOK
# ==========================================

class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ----------------------------------------------------
    # /panel setup (Beállítások)
    # ----------------------------------------------------
    @app_commands.command(name="panel_setup", description="Beállítja a dinamikus Queue kategóriát és a log csatornát.")
    @app_commands.describe(
        kategoria="A kategória, amelyben a dinamikus Queue csatornák létrejönnek.",
        log_csatorna="A csatorna, ahová a queue naplózások kerülnek (opcionális)."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_setup(
        self, 
        interaction: discord.Interaction, 
        kategoria: discord.CategoryChannel,
        log_csatorna: discord.TextChannel | None = None
    ) -> None:
        PANEL_CONFIG["queue_category_id"] = kategoria.id
        if log_csatorna:
            PANEL_CONFIG["log_channel_id"] = log_csatorna.id

        embed = discord.Embed(
            title="⚙️ Panel Rendszer Beállítva",
            description=(
                f"✅ **Queue Kategória:** {kategoria.mention} (`{kategoria.id}`)\n"
                f"✅ **Log Csatorna:** {log_csatorna.mention if log_csatorna else '*Nincs megadva*'}"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
                "*(A rendszer automatikusan létrehoz egy ideiglenes csatornát, amit a teszt végeztével töröl.)*"
            ),
            color=discord.Color.gold() if is_legacy else discord.Color.blue()
        )
        embed.set_footer(text="NeonTiers.hu • Dinamikus Queue Rendszer")

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
