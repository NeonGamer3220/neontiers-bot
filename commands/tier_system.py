"""
NeonTiers Bot - Tier System Panel Parancsok és Inaktivitási Figyelő (commands/tier_system.py)
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import time
import asyncio

from commands.tier_ui import PanelSelectView
from commands.tier_utils import INACTIVE_TICKETS, archive_channel, COOLDOWNS, is_dm_optout
from config import STAFF_ROLE_ID, REGULATOR_ROLE_ID, get_gamemode_display_name


class TierSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.inactivity_checker.start()
        self.cooldown_notifier.start()

    def cog_unload(self):
        self.inactivity_checker.cancel()
        self.cooldown_notifier.cancel()

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
                last_act = data.get("last_activity", now)
                diff = now - last_act

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
                    owner = channel.guild.get_member(data["owner_id"])
                    await archive_channel(channel, owner or self.bot.user, reason="Automatikus lezárás inaktivitás miatt (48h + 4h)")
                    await channel.delete(reason="Automatikus lezárás inaktivitás miatt (48h + 4h)")
            except Exception:
                pass

        for ch_id in to_delete:
            INACTIVE_TICKETS.pop(ch_id, None)

    @inactivity_checker.before_loop
    async def before_inactivity_checker(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def cooldown_notifier(self):
        now = time.time()
        expired = [(key, expiry) for key, expiry in list(COOLDOWNS.items()) if expiry <= now]

        for (user_id, gamemode), _ in expired:
            COOLDOWNS.pop((user_id, gamemode), None)

            if is_dm_optout(user_id):
                continue

            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                label = get_gamemode_display_name(gamemode)
                embed = discord.Embed(
                    title="⏳ Lejárt a várakozási időd!",
                    description=f"Lejárt a tesztelési várakozási időd a(z) **{label}** játékmódban, most már újra jelentkezhetsz tesztre!",
                    color=discord.Color.green()
                )
                await user.send(embed=embed)
            except Exception:
                pass

    @cooldown_notifier.before_loop
    async def before_cooldown_notifier(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        ch_id = message.channel.id
        if ch_id in INACTIVE_TICKETS:
            data = INACTIVE_TICKETS[ch_id]
            data["last_activity"] = time.time()
            if data["warned"]:
                data["warned"] = False
                await message.channel.send("✅ Új üzenet érkezett, a 48 órás visszaszámlálás újrakezdődött!")

    def _is_regulator_or_staff(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        role_ids = {r.id for r in member.roles}
        return bool(role_ids & {STAFF_ROLE_ID, REGULATOR_ROLE_ID})

    @app_commands.command(name="ticketadd", description="Hozzáad egy felhasználót a jelenlegi tickethez/csatornához.")
    @app_commands.describe(user="A hozzáadandó felhasználó.")
    async def ticketadd(self, interaction: discord.Interaction, user: discord.Member):
        if not self._is_regulator_or_staff(interaction.user):
            return await interaction.response.send_message("❌ Csak regulatorok vagy staff tagok adhatnak hozzá felhasználót egy tickethez!", ephemeral=True)

        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("❌ Ez a parancs csak szöveges csatornában/ticketben használható!", ephemeral=True)

        try:
            await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Nem sikerült hozzáadni: `{e}`", ephemeral=True)

        if interaction.channel.id in INACTIVE_TICKETS:
            INACTIVE_TICKETS[interaction.channel.id]["last_activity"] = time.time()
            INACTIVE_TICKETS[interaction.channel.id]["warned"] = False

        await interaction.response.send_message(f"✅ {user.mention} hozzáadva a tickethez {interaction.user.mention} által.")

    @app_commands.command(name="ticketremove", description="Eltávolít egy felhasználót a jelenlegi tickethez/csatornából.")
    @app_commands.describe(user="Az eltávolítandó felhasználó.")
    async def ticketremove(self, interaction: discord.Interaction, user: discord.Member):
        if not self._is_regulator_or_staff(interaction.user):
            return await interaction.response.send_message("❌ Csak regulatorok vagy staff tagok távolíthatnak el felhasználót egy tickeből!", ephemeral=True)

        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("❌ Ez a parancs csak szöveges csatornában/ticketben használható!", ephemeral=True)

        try:
            await interaction.channel.set_permissions(user, view_channel=False, send_messages=False, read_message_history=False)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Nem sikerült eltávolítani: `{e}`", ephemeral=True)

        await interaction.response.send_message(f"✅ {user.mention} eltávolítva a ticketből {interaction.user.mention} által.")

    @app_commands.command(name="archives", description="Kilistázza a legutóbb archivált ticketeket.")
    @app_commands.describe(count="Hány legutóbbi archívumot listázzon ki (max 25).", jatekos="Szűrés Minecraft név / csatornanév alapján (opcionális).")
    @app_commands.checks.has_permissions(administrator=True)
    async def archives(self, interaction: discord.Interaction, count: int = 10, jatekos: str = None):
        import json, os
        if not os.path.exists("ticket_archives.json"):
            return await interaction.response.send_message("📭 Még nincs archivált ticket.", ephemeral=True)
        try:
            with open("ticket_archives.json", "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            return await interaction.response.send_message("❌ Nem sikerült beolvasni az archívum indexet.", ephemeral=True)

        if jatekos:
            index = [e for e in index if jatekos.lower() in e.get("channel_name", "").lower()]

        index = list(reversed(index))[:max(1, min(count, 25))]
        if not index:
            return await interaction.response.send_message("📭 Nincs találat.", ephemeral=True)

        embed = discord.Embed(title="🗄️ Legutóbbi Archivált Ticketek", color=discord.Color.dark_grey())
        for e in index:
            jump = f"https://discord.com/channels/{interaction.guild.id}/{e.get('archive_channel_id')}/{e.get('archive_message_id')}"
            embed.add_field(
                name=f"#{e.get('channel_name')}",
                value=f"Lezárta: {e.get('closed_by')}\nOk: {e.get('reason') or '-'}\nÜzenetek: {e.get('message_count')}\n[Megnyitás]({jump})",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
            description=f"Válaszd ki a(z) **{tipus}** High Tier szintet az alábbi menüből a ticket nyitásához.",
            color=discord.Color.purple() if tipus == "Modern" else discord.Color.dark_purple()
        )
        embed.set_footer(text="NeonTiers Management System")
        await target_channel.send(embed=embed, view=PanelSelectView(tipus, "hightest"))
        await interaction.response.send_message(f"✅ {tipus} High-Test panel elküldve ide: {target_channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TierSystemCog(bot))
