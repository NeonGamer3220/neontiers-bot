"""
NeonTiers Bot - Tier System Panel Parancsok és Inaktivitási Figyelő (commands/tier_system.py)
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import time

from commands.tier_ui import PanelSelectView
from commands.tier_utils import INACTIVE_TICKETS


class TierSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.inactivity_checker.start()

    def cog_unload(self):
        self.inactivity_checker.cancel()

    @tasks.loop(minutes=5)
    async def inactivity_checker(self):
        now = time.time()
        to_delete = []
        for ch_id, data in list(INACTIVE_TICKETS.items()):
            channel = self.bot.get_channel(ch_id)
            if not channel:
                to_delete.append(ch_id)
                continue

            try:
                async for message in channel.history(limit=1):
                    last_msg_time = message.created_at.timestamp()
                    diff = now - last_msg_time

                    if not data["warned"] and diff >= 48 * 3600:
                        data["warned"] = True
                        data["warn_time"] = now
                        owner = channel.guild.get_member(data["owner_id"])
                        mention = owner.mention if owner else f"<@{data['owner_id']}>"
                        await channel.send(f"⚠️ {mention} Mivel 48 órája nem érkezett üzenet, ez a ticket 4 óra múlva automatikusan lezárásra kerül, ha nem válaszolsz!")
                    
                    elif data["warned"] and (now - data["warn_time"]) >= 4 * 3600:
                        await channel.send("🔒 Az inaktivitás miatt a ticket automatikusan lezárásra került.")
                        to_delete.append(ch_id)
                        await asyncio.sleep(2)
                        await channel.delete(reason="Automatikus lezárás inaktivitás miatt (48h + 4h)")
            except Exception:
                pass

        for ch_id in to_delete:
            INACTIVE_TICKETS.pop(ch_id, None)

    @inactivity_checker.before_loop
    async def before_inactivity_checker(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        ch_id = message.channel.id
        if ch_id in INACTIVE_TICKETS:
            data = INACTIVE_TICKETS[ch_id]
            if data["warned"]:
                data["warned"] = False
                await message.channel.localesend if hasattr(message.channel, 'localesend') else message.channel.send("✅ Új üzenet érkezett, a 48 órás visszaszámlálás újrakezdődött!")

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
