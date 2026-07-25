"""
NeonTiers Bot - Panels Modul (commands/panels.py)
Modern és Legacy alapú /pingpanel, /queuepanel és /hightestpanel parancsok dropdown (select menu) támogatással.
"""

import discord
from discord import app_commands
from discord.ext import commands
import datetime

from config import TICKET_TYPES, LEGACY_TICKET_TYPES, ALL_TICKET_TYPES, get_gamemode_display_name
from commands.tier_utils import ACTIVE_QUEUES, get_ticket_category, THEME_LIGHT_PURPLE
from commands.tier_ui import QueueActiveView

class PanelSelectView(discord.ui.View):
    def __init__(self, mode_type: str, action_type: str):
        super().__init__(timeout=None)
        self.mode_type = mode_type
        self.action_type = action_type
        
        types_list = LEGACY_TICKET_TYPES if mode_type.lower() == "legacy" else TICKET_TYPES
        
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
            self.add_item(PanelSelect(options, mode_type, action_type))


class PanelSelect(discord.ui.Select):
    def __init__(self, options, mode_type: str, action_type: str):
        placeholders = {
            "ping": f"Válassz értesítési kategóriát ({mode_type.upper()})...",
            "queue": f"Válassz játékmódot a várólistához ({mode_type.upper()})...",
            "hightest": f"Válassz High Tier tesztet ({mode_type.upper()})..."
        }
        super().__init__(
            placeholder=placeholders.get(action_type, "Válassz..."),
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"panel_{action_type}_{mode_type}_{discord.utils.utcnow().timestamp()}"
        )
        self.action_type = action_type
        self.mode_type = mode_type

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        label = get_gamemode_display_name(key)
        is_legacy = (self.mode_type.lower() == "legacy")

        if self.action_type == "ping":
            await interaction.response.send_message(f"✅ Sikeresen feliratkoztál / módosítottad a pinget ehhez: **{label}** ({self.mode_type})!", ephemeral=True)
            return

        # Várólista vagy High-Test esetén csatornát nyitunk
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = get_ticket_category(guild, is_legacy)
        
        tester_role_name = f"{label} Tester"
        tester_role = discord.utils.get(guild.roles, name=tester_role_name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if tester_role:
            overwrites[tester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            queue_chan = await guild.create_text_channel(
                name=f"queue-{key.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"NeonTiers Várólista - {label} ({self.mode_type})"
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Nem sikerült csatornát létrehozni: `{e}`", ephemeral=True)

        queue_role = discord.utils.get(guild.roles, name=f"{label} Queue")
        q_ping = queue_role.mention if queue_role else f"@{label} Queue"

        ACTIVE_QUEUES[queue_chan.id] = {
            "players": [], 
            "testers": [interaction.user.id], 
            "gamemode": key,
            "msg_id": None
        }

        emoji_str = "🎮"
        for l, k, e in ALL_TICKET_TYPES:
            if k == key:
                emoji_str = str(e)
                break

        desc = f"**Helyek:** 0/20\n\n**Játékosok a várólistán:**\n*- Üres -*\n\n**Aktív Teszterek:**\n🛡️ <@{interaction.user.id}>\n"
        embed = discord.Embed(
            title=f"{emoji_str} {label} Várólista ({self.mode_type})", 
            description=desc, 
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        
        msg = await queue_chan.send(content=f"🔔 {q_ping}", embed=embed, view=QueueActiveView(key, tester_role))
        ACTIVE_QUEUES[queue_chan.id]["msg_id"] = msg.id
        await interaction.followup.send(f"✅ Várólista csatorna sikeresen megnyitva: {queue_chan.mention}", ephemeral=True)


class PanelsCog(commands.Cog):
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
    await bot.add_cog(PanelsCog(bot))
