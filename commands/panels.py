"""
NeonTiers Bot - Panels Parancsok (commands/panels.py)
Modern és Legacy alapú /pingpanel, /queuepanel és /hightestpanel parancsok dropdown (select menu) támogatással.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import TICKET_TYPES, LEGACY_TICKET_TYPES


class PingSelectView(discord.ui.View):
    def __init__(self, mode_type: str):
        super().__init__(timeout=None)
        types_list = LEGACY_TICKET_TYPES if mode_type == "legacy" else TICKET_TYPES
        
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
            self.add_item(PingSelect(options, mode_type))


class PingSelect(discord.ui.Select):
    def __init__(self, options, mode_type):
        super().__init__(
            placeholder=f"Válassz értesítési kategóriát ({mode_type.upper()})...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"ping_select_{mode_type}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_message(f"✅ Sikeresen feliratkoztál/leiratkoztál erről: `{selected}`!", ephemeral=True)


class QueueSelectView(discord.ui.View):
    def __init__(self, mode_type: str):
        super().__init__(timeout=None)
        types_list = LEGACY_TICKET_TYPES if mode_type == "legacy" else TICKET_TYPES
        
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
            self.add_item(QueueSelect(options, mode_type))


class QueueSelect(discord.ui.Select):
    def __init__(self, options, mode_type):
        super().__init__(
            placeholder=f"Válassz játékmódot a várólistához ({mode_type.upper()})...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"queue_select_{mode_type}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_message(f"✅ Várólista kérelem rögzítve ehhez: `{selected}`!", ephemeral=True)


class HighTestSelectView(discord.ui.View):
    def __init__(self, mode_type: str):
        super().__init__(timeout=None)
        types_list = LEGACY_TICKET_TYPES if mode_type == "legacy" else TICKET_TYPES
        
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
            self.add_item(HighTestSelect(options, mode_type))


class HighTestSelect(discord.ui.Select):
    def __init__(self, options, mode_type):
        super().__init__(
            placeholder=f"Válassz High Tier tesztet ({mode_type.upper()})...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"hightest_select_{mode_type}"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_message(f"✅ High Tier teszt kérelem elküldve ehhez: `{selected}`!", ephemeral=True)


class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Elküldi a ping panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def pingpanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"🔔 Értesítések & Pingek ({tipus.capitalize()})",
            description=f"Válaszd ki az alábbi legördülő menüből a(z) **{tipus.upper()}** értesítési szerepet!",
            color=discord.Color.blue() if tipus == "modern" else discord.Color.dark_blue()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PingSelectView(tipus))
        await interaction.response.send_message(f"✅ {tipus.capitalize()} Ping panel elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="queuepanel", description="Elküldi a queue panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"🎮 Várólista Panel ({tipus.capitalize()})",
            description=f"Válaszd ki a(z) **{tipus.upper()}** játékmódot a várólistához az alábbi menüből.",
            color=discord.Color.green() if tipus == "modern" else discord.Color.dark_green()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=QueueSelectView(tipus))
        await interaction.response.send_message(f"✅ {tipus.capitalize()} Queue panel elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="hightestpanel", description="Elküldi a high tier teszt panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="modern"),
        app_commands.Choice(name="Legacy", value="legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def hightestpanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"⚔️ High Tier Tesztek ({tipus.capitalize()})",
            description=f"Válaszd ki a(z) **{tipus.upper()}** High Tier tesztet az alábbi menüből.",
            color=discord.Color.purple() if tipus == "modern" else discord.Color.dark_purple()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=HighTestSelectView(tipus))
        await interaction.response.send_message(f"✅ {tipus.capitalize()} High-Test panel elküldve ide: {target_channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelsCog(bot))
