"""
NeonTiers Bot - Tier System Panel Parancsok (commands/tier_system.py)
Modern és Legacy alapú /pingpanel, /queuepanel és /hightestpanel parancsok dropdown támogatással.
"""

import discord
from discord import app_commands
from discord.ext import commands

from commands.tier_ui import PanelSelectView


class TierSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Elküldi a ping panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="Modern"),
        app_commands.Choice(name="Legacy", value="Legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def pingpanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"🔔 Értesítések & Pingek ({tipus})",
            description=f"Válaszd ki az alábbi legördülő menüből a(z) **{tipus}** kategóriát az értesítésekhez!",
            color=discord.Color.blue() if tipus == "Modern" else discord.Color.dark_blue()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PanelSelectView(tipus, "ping"))
        await interaction.response.send_message(f"✅ {tipus} Ping panel elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="queuepanel", description="Elküldi a queue panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="Modern"),
        app_commands.Choice(name="Legacy", value="Legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"🎮 Várólista Panel ({tipus})",
            description=f"Válaszd ki a(z) **{tipus}** játékmódot a várólista megnyitásához az alábbi menüből.",
            color=discord.Color.green() if tipus == "Modern" else discord.Color.dark_green()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PanelSelectView(tipus, "queue"))
        await interaction.response.send_message(f"✅ {tipus} Queue panel elküldve ide: {target_channel.mention}", ephemeral=True)

    @app_commands.command(name="hightestpanel", description="Elküldi a high tier teszt panelt Modern vagy Legacy opcióval (dropdown).")
    @app_commands.describe(
        tipus="Válaszd ki, hogy Modern vagy Legacy panelt szeretnél.",
        csatorna="A célcsatorna, ahová a panelt küldeni kell."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Modern", value="Modern"),
        app_commands.Choice(name="Legacy", value="Legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def hightestpanel(self, interaction: discord.Interaction, tipus: str, csatorna: discord.TextChannel = None):
        target_channel = csatorna or interaction.channel
        embed = discord.Embed(
            title=f"⚔️ High Tier Tesztek ({tipus})",
            description=f"Válaszd ki a(z) **{tipus}** High Tier tesztet az alábbi menüből a sor indításához.",
            color=discord.Color.purple() if tipus == "Modern" else discord.Color.dark_purple()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PanelSelectView(tipus, "hightest"))
        await interaction.response.send_message(f"✅ {tipus} High-Test panel elküldve ide: {target_channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TierSystemCog(bot))
