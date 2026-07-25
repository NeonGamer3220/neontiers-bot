"""
NeonTiers Bot - Panels Parancsok (commands/panels.py)
A gombos alapú /pingpanel, /queuepanel és /hightestpanel parancsok.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import STAFF_ROLE_ID, REGULATOR_ROLE_ID


class PingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Queue Ping Feliratkozás", style=discord.ButtonStyle.primary, custom_id="ping_panel_subscribe")
    async def subscribe_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Sikeresen feliratkoztál/leiratkoztál az értesítésekről!", ephemeral=True)


class QueuePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 Várólista Nyitása", style=discord.ButtonStyle.success, custom_id="queue_panel_open")
    async def open_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Várólista menü megnyitva!", ephemeral=True)


class HighTestPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⚔️ High Tier Teszt Kérelem", style=discord.ButtonStyle.danger, custom_id="hightest_panel_request")
    async def hightest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ High Tier kérelem rögzítve/elindítva!", ephemeral=True)


class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Elküldi a ping panelt interaktív gombokkal.")
    @app_commands.describe(csatorna="A célcsatorna, ahová a panelt küldeni kell.")
    @app_commands.checks.has_permissions(administrator=True)
    async def pingpanel(self, interaction: discord.Interaction, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title="🔔 Értesítések & Pingek",
            description="Kattints az alábbi gombra az értesítési szerepek kezeléséhez!",
            color=discord.Color.blue()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PingPanelView())
        await interaction.response.send_message(f"✅ Ping panel sikeresen elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="queuepanel", description="Elküldi a queue panelt interaktív gombokkal.")
    @app_commands.describe(csatorna="A célcsatorna, ahová a panelt küldeni kell.")
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title="🎮 Várólista Panel",
            description="Kattints a gombra a várakozási sorok eléréséhez.",
            color=discord.Color.green()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=QueuePanelView())
        await interaction.response.send_message(f"✅ Queue panel sikeresen elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="hightestpanel", description="Elküldi a magas tier teszt panelt gombokkal.")
    @app_commands.describe(csatorna="A célcsatorna, ahová a panelt küldeni kell.")
    @app_commands.checks.has_permissions(administrator=True)
    async def hightestpanel(self, interaction: discord.Interaction, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title="⚔️ High Tier Tesztek",
            description="Magas szintű tesztelési kérelmek és információk.",
            color=discord.Color.purple()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=HighTestPanelView())
        await interaction.response.send_message(f"✅ High-Test panel sikeresen elküldve ide: {target_channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelsCog(bot))
