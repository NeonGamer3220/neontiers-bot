import discord
from discord.ext import commands
from discord import app_commands
import datetime

class QueuePanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="queuepanel", description="Megnyitja vagy elküldi a queue panelt.")
    @app_commands.describe(panel_type="A panel típusa (Modern vagy Legacy)")
    @app_commands.choices(panel_type=[
        app_commands.Choice(name="Modern", value="Modern"),
        app_commands.Choice(name="Legacy", value="Legacy")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction, panel_type: str):
        # Előre jelezzük a Discordnak, hogy a bot dolgozik (megelőzi az időtúllépési hibát)
        await interaction.response.defer(thinking=True, ephemeral=True)

        embed = discord.Embed(
            title=f"📋 NeoTiers Queue – {panel_type}",
            description=f"Kattints az alábbi gombokra a(z) **{panel_type}** sorba való csatlakozáshoz vagy kilépéshez.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text="NeoTiers Matchmaking System")

        view = QueuePanelView(panel_type)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class QueuePanelView(discord.ui.View):
    def __init__(self, panel_type: str):
        super().__init__(timeout=None)
        self.panel_type = panel_type

    @discord.ui.button(label="➕ Csatlakozás a sorhoz", style=discord.ButtonStyle.success, custom_id="queue:join")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"✅ Sikeresen csatlakoztál a(z) **{self.panel_type}** sorhoz!", ephemeral=True)

    @discord.ui.button(label="➖ Kilépés a sorból", style=discord.ButtonStyle.danger, custom_id="queue:leave")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ Kiléptél a(z) **{self.panel_type}** sorból.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(QueuePanelCog(bot))
