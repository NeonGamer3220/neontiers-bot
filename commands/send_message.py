"""
NeonTiers Bot - SendMessage Parancs (commands/send_message.py)
/sendmessage <discordid> <típus> <csatorna>

A parancs DM-ben elküldi a megfelelő szöveget a (még a szerveren kívül lévő)
játékosnak, majd amikor a játékos belép a szerverre, a bot automatikusan
hozzáadja a megadott csatornához. "Magas ticket" típusnál 24 óra után
emlékeztető DM-et is küld, ha a játékos addig nem lépett be.
"""

import json
import logging
import os
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("neontiers.commands.send_message")

PENDING_FILE = "pending_invites.json"
INVITE_URL = "https://discord.gg/7fanAQDxaN"

MESSAGE_TEMPLATES = {
    "magas": (
        "Szia! Ki lettél pörgetve egy magas tesztre a NeonTiers.hu szerverén, ha szeretnéd lejátszani, "
        "48 órád lesz belépni a szerverre, ekkor a bot automatikusan hozzáad a kívánt tickethez, "
        "illetve a bot 24 óra múlva küld egy ismétlő üzenetet!\n"
        f"Csatlakozás: {INVITE_URL}"
    ),
    "tournament": (
        "Szia! A NeonTiers.hu szerverén jelenleg egy tournament van folyamatban, ha szeretnéd lejátszani, "
        "24 órád lesz belépni a szerverre, ekkor a bot automatikusan hozzáad a mérkőzésedhez.\n"
        f"Csatlakozás: {INVITE_URL}"
    )
}

REMINDER_TEMPLATE = (
    "⏰ Emlékeztető! Még mindig vár rád egy magas teszt a NeonTiers.hu szerverén. "
    "A 48 órás határidődből már eltelt 24 óra, ne felejts el belépni!\n"
    f"Csatlakozás: {INVITE_URL}"
)

WINDOW_SECONDS = {
    "magas": 48 * 3600,
    "tournament": 24 * 3600
}


def _load_pending() -> list:
    if not os.path.exists(PENDING_FILE):
        return []
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_pending(data: list):
    try:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class SendMessageCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @app_commands.command(
        name="sendmessage",
        description="DM küldése egy játékosnak (Magas ticket / Tournament), automatikus csatorna-hozzáadással belépéskor."
    )
    @app_commands.describe(
        discordid="A célszemély Discord ID-ja.",
        tipus="Az üzenet típusa.",
        csatorna="A csatorna, amihez a bot automatikusan hozzáadja a játékost, amint belép a szerverre."
    )
    @app_commands.choices(tipus=[
        app_commands.Choice(name="Magas ticket", value="magas"),
        app_commands.Choice(name="Tournament", value="tournament"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def sendmessage(
        self,
        interaction: discord.Interaction,
        discordid: str,
        tipus: app_commands.Choice[str],
        csatorna: discord.TextChannel
    ) -> None:
        try:
            user_id = int(discordid.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Érvénytelen Discord ID!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        try:
            target_user = await self.bot.fetch_user(user_id)
        except Exception:
            return await interaction.followup.send("❌ Nem található felhasználó ezzel az ID-val!", ephemeral=True)

        message_text = MESSAGE_TEMPLATES[tipus.value]

        try:
            await target_user.send(message_text)
        except discord.Forbidden:
            return await interaction.followup.send(f"❌ {target_user.mention} letiltotta a privát üzeneteket, nem sikerült kézbesíteni!", ephemeral=True)
        except Exception as exc:
            log.error("Hiba a DM küldésekor: %s", exc)
            return await interaction.followup.send(f"❌ Hiba történt a DM küldésekor: `{exc}`", ephemeral=True)

        pending = _load_pending()
        pending = [p for p in pending if not (p["discord_id"] == user_id and p["type"] == tipus.value)]
        pending.append({
            "discord_id": user_id,
            "type": tipus.value,
            "channel_id": csatorna.id,
            "guild_id": interaction.guild.id,
            "created_at": time.time(),
            "reminded": False
        })
        _save_pending(pending)

        await interaction.followup.send(
            f"✅ Üzenet elküldve {target_user.mention} részére ({tipus.name}). Amint belép a szerverre, automatikusan hozzáadjuk a(z) {csatorna.mention} csatornához.",
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        pending = _load_pending()
        matches = [p for p in pending if p["discord_id"] == member.id and p.get("guild_id", member.guild.id) == member.guild.id]
        if not matches:
            return

        remaining = [p for p in pending if p not in matches]

        for entry in matches:
            channel = member.guild.get_channel(entry["channel_id"])
            if not channel:
                continue
            try:
                await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
                label = "High Test" if entry["type"] == "magas" else "Tournament"
                await channel.send(f"👋 {member.mention} csatlakozott! ({label})")
            except Exception as exc:
                log.error("Hiba a tag hozzáadásakor a csatornához: %s", exc)

        _save_pending(remaining)

    @tasks.loop(minutes=30)
    async def reminder_loop(self):
        pending = _load_pending()
        if not pending:
            return

        now = time.time()
        changed = False
        kept = []

        for entry in pending:
            window = WINDOW_SECONDS.get(entry["type"], 48 * 3600)
            age = now - entry["created_at"]

            if age >= window:
                # Lejárt a határidő, eltávolítjuk a várólistáról
                changed = True
                continue

            if entry["type"] == "magas" and not entry.get("reminded") and age >= 24 * 3600:
                try:
                    user = await self.bot.fetch_user(entry["discord_id"])
                    await user.send(REMINDER_TEMPLATE)
                except Exception:
                    pass
                entry["reminded"] = True
                changed = True

            kept.append(entry)

        if changed:
            _save_pending(kept)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SendMessageCog(bot))
