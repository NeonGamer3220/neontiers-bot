import discord
from discord.ext import commands
from discord import app_commands
import datetime

from config import (
    ALL_TICKET_TYPES, LEGACY_TICKET_TYPES, get_gamemode_display_name
)
from commands.tier_ui import QueueActiveView
from tier_utils import ACTIVE_QUEUES, get_ticket_category, THEME_LIGHT_PURPLE

class OpenQueueModal(discord.ui.Modal, title="Várólista Nyitása"):
    def __init__(self, mode_key: str, mode_label: str, emoji_str: str, is_legacy: bool):
        super().__init__()
        self.mode_key = mode_key
        self.mode_label = mode_label
        self.emoji_str = emoji_str
        self.is_legacy = is_legacy

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = get_ticket_category(guild, self.is_legacy)
        
        tester_role_name = f"{self.mode_label} Tester"
        tester_role = discord.utils.get(guild.roles, name=tester_role_name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if tester_role:
            overwrites[tester_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            queue_chan = await guild.create_text_channel(
                name=f"queue-{self.mode_key.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"NeonTiers Várólista - {self.mode_label}"
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Nem sikerült csatornát létrehozni: `{e}`", ephemeral=True)

        queue_role = discord.utils.get(guild.roles, name=f"{self.mode_label} Queue")
        q_ping = queue_role.mention if queue_role else f"@{self.mode_label} Queue"

        ACTIVE_QUEUES[queue_chan.id] = {
            "players": [], 
            "testers": [interaction.user.id], 
            "gamemode": self.mode_key,
            "msg_id": None
        }

        desc = f"**Helyek:** 0/20\n\n**Játékosok a várólistán:**\n*- Üres -*\n\n**Aktív Teszterek:**\n🛡️ <@{interaction.user.id}>\n"
        embed = discord.Embed(
            title=f"{self.emoji_str} {self.mode_label} Várólista", 
            description=desc, 
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        
        msg = await queue_chan.send(content=f"🔔 {q_ping}", embed=embed, view=QueueActiveView(self.mode_key, tester_role))
        ACTIVE_QUEUES[queue_chan.id]["msg_id"] = msg.id
        await interaction.followup.send(f"✅ Várólista csatorna megnyitva: {queue_chan.mention}", ephemeral=True)


class OpenQueuePanelView(discord.ui.View):
    def __init__(self, is_legacy: bool = False):
        super().__init__(timeout=None)
        self.is_legacy = is_legacy
        types = LEGACY_TICKET_TYPES if is_legacy else TICKET_TYPES
        
        for label, key, emoji_raw in types[:25]:  # Discord limit: max 25 elem select-ben
            emoji_str = str(emoji_raw)
            if emoji_str.isdigit():
                emoji_str = discord.PartialEmoji(name=label.replace(" ", ""), id=int(emoji_str))
            self.gamemode_select.add_option(label=label, value=key, emoji=emoji_str)

    @discord.ui.select(placeholder="Válassz játékmódot a várólistához...", min_values=1, max_values=1)
    async def gamemode_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        key = select.values[0]
        label = get_gamemode_display_name(key)
        emoji_str = "🎮"
        for l, k, e in ALL_TICKET_TYPES:
            if k == key:
                emoji_str = str(e)
                break
        
        modal = OpenQueueModal(mode_key=key, mode_label=label, emoji_str=emoji_str, is_legacy=self.is_legacy)
        await interaction.response.send_modal(modal)


class TierSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="queuepanel", description="Modern tier várólista panel kihelyezése.")
    @app_commands.checks.has_permissions(administrator=True)
    async def queuepanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ NeonTiers Modern Várólista Panel",
            description="Válassz a lenyíló menüből játékmódot, hogy megnyisd a tesztelési várólistát!",
            color=discord.Color(THEME_LIGHT_PURPLE)
        )
        embed.set_footer(text="NeoTiers Official Management")
        await interaction.channel.send(embed=embed, view=OpenQueuePanelView(is_legacy=False))
        await interaction.response.send_message("✅ Várólista panel sikeresen elhelyezve!", ephemeral=True)

    @app_commands.command(name="legacyqueuepanel", description="Legacy tier várólista panel kihelyezése.")
    @app_commands.checks.has_permissions(administrator=True)
    async def legacyqueuepanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📜 NeonTiers Legacy Várólista Panel",
            description="Válassz a lenyíló menüből legacy játékmódot a várólista nyitásához!",
            color=discord.Color.dark_blue()
        )
        embed.set_footer(text="NeoTiers Legacy Management")
        await interaction.channel.send(embed=embed, view=OpenQueuePanelView(is_legacy=True))
        await interaction.response.send_message("✅ Legacy várólista panel sikeresen elhelyezve!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TierSystemCog(bot))
