"""
NeonTiers Main Bot - main.py
- Fiók összekapcsolás & Verifikáció
- /sendmessage parancs (Magas teszt & Tournament értesítések)
- Automatikus ticket-hozzáadás belépéskor
- 24 órás emlékeztető háttérfolyamat
"""

from __future__ import annotations

import logging
import sys
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import config
from database import arun, db

# Logging beállítása
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("neontiers.main")

# Bot Intention-ök beállítása (SERVER MEMBERS INTENT SZÜKSÉGES)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================================================================
# KONSTANSOK ÉS ÜZENET SABLONOK
# ======================================================================

INVITE_LINK = "https://discord.gg/7fanAQDxaN"

TEXT_MAGAS = (
    "Szia! Ki lettél pörgetve egy magas tesztre a NeonTiers.hu szerverén, "
    "ha szeretnéd lejátszani, 48 órád lesz belépni a szerverre, ekkor a bot "
    "automatikusan hozzáad a kívánt tickethez, illetve a bot 24 óra múlva küld egy ismétlő üzenetet!\n"
    f"Csatlakozás: {INVITE_LINK}"
)

TEXT_TOURNAMENT = (
    "Szia! Jelenleg egy tournament folyik a NeonTiers.hu szerverén amire te jelentkeztél, "
    "hogyha szeretnéd lejátszani a mérkőzésed, 24 órád lesz belépni a szerverre, ekkor a bot "
    "automatikusan hozzáad a tournament ticketedhez!\n"
    f"Csatlakozás: {INVITE_LINK}"
)

# ======================================================================
# BOT ESEMÉNYEK (EVENTS)
# ======================================================================

@bot.event
async def on_ready() -> None:
    log.info("Fő bot elindult: %s (ID: %s)", bot.user, bot.user.id if bot.user else 0)
    
    # 24 órás emlékeztető ciklus indítása
    if not reminder_loop.is_running():
        reminder_loop.start()
        log.info("Reminder loop elindítva.")

    # Parancsok szinkronizálása a megadott Guild-re
    try:
        guild = discord.Object(id=config.guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log.info("Sikeresen szinkronizálva %d parancs a szerverre.", len(synced))
    except Exception as exc:
        log.error("Hiba a parancsok szinkronizálásakor: %s", exc)


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Amikor egy játékos csatlakozik a Discord szerverre, ellenőrizzük, hogy van-e függőben lévő ticketje."""
    try:
        pending_list = await arun(db.get_pending_invite_for_user, member.id)
        if not pending_list:
            return

        for invite in pending_list:
            channel_id = int(invite.get("ticket_channel_id", 0))
            channel = member.guild.get_channel(channel_id)

            if isinstance(channel, discord.TextChannel):
                # Olvasási és írási jog megadása a belépő játékosnak
                await channel.set_permissions(member, read_messages=True, send_messages=True)
                
                embed = discord.Embed(
                    title="👋 Megérkezett a hiányzó játékos!",
                    description=f"<@{member.id}> belépett a szerverre, ezért automatikusan hozzáadásra került a tickethez.",
                    color=discord.Color.green()
                )
                await channel.send(content=f"🔔 <@{member.id}>", embed=embed)
                
                # Befejezettnek jelöljük az adatbázisban
                await arun(db.mark_invite_completed, invite["id"])
                log.info("Játékos (%s) sikeresen hozzáadva a tickethez (%s).", member.id, channel.id)
    except Exception as exc:
        log.error("Hiba az on_member_join feldolgozása közben: %s", exc)

# ======================================================================
# HÁTTÉRFOLYAMATOK (TASKS)
# ======================================================================

@tasks.loop(minutes=30)
async def reminder_loop() -> None:
    """24 óra elteltével újra elküldi a 'Magas ticket' emlékeztetőt a hiányzó játékosnak."""
    try:
        due_invites = await arun(db.get_due_reminders)
        for invite in due_invites:
            target_id = int(invite["discord_id"])
            try:
                user = await bot.fetch_user(target_id)
                if user:
                    await user.send(f"🔔 **Emlékeztető (24 óra telt el):**\n\n{TEXT_MAGAS}")
                    await arun(db.mark_reminder_sent, invite["id"])
                    log.info("24h emlékeztető elküldve a felhasználónak: %s", target_id)
            except Exception as exc:
                log.warning("Emlékeztető DM küldése sikertelen (%s): %s", target_id, exc)
    except Exception as exc:
        log.error("Hiba a reminder_loop futása közben: %s", exc)

# ======================================================================
# SLASH PARANCSOK
# ======================================================================

@bot.tree.command(name="sendmessage", description="DM üzenet küldése és automatikus ticket-hozzáadás beállítása.")
@app_commands.choices(type=[
    app_commands.Choice(name="Magas ticket", value="magas"),
    app_commands.Choice(name="Tournament ticket", value="tournament")
])
async def sendmessage_cmd(
    interaction: discord.Interaction, 
    discordid: str, 
    type: app_commands.Choice[str], 
    ticket: discord.TextChannel
) -> None:
    await interaction.response.defer(ephemeral=True)
    
    try:
        target_id = int(discordid)
    except ValueError:
        await interaction.followup.send("❌ Érvénytelen Discord ID formátum!", ephemeral=True)
        return

    msg_text = TEXT_MAGAS if type.value == "magas" else TEXT_TOURNAMENT

    # DM üzenet kiküldése
    dm_sent = False
    try:
        user = await bot.fetch_user(target_id)
        if user:
            await user.send(msg_text)
            dm_sent = True
    except Exception as exc:
        log.warning("Nem sikerült DM-et küldeni a felhasználónak (%s): %s", target_id, exc)

    # Rögzítés a Supabase adatbázisban
    await arun(db.create_pending_invite, target_id, type.value, ticket.id)

    status_msg = "✅ DM üzenet elküldve" if dm_sent else "⚠️ DM üzenet nem küldhető el (zárt DM)"
    await interaction.followup.send(
        f"{status_msg} és a feladat rögzítve!\n"
        f"• **Célpont:** <@{target_id}>\n"
        f"• **Típus:** {type.name}\n"
        f"• **Ticket:** {ticket.mention}",
        ephemeral=True
    )


@bot.tree.command(name="syncguild", description="Parancsok azonnali szinkronizálása erre a szerverre.")
async def syncguild_cmd(interaction: discord.Interaction) -> None:
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Ehhez nincs jogosultságod!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    if interaction.guild:
        bot.tree.copy_global_to(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Sikeresen szinkronizálva {len(synced)} parancs ezen a szerveren!", ephemeral=True)

# ======================================================================
# INDÍTÁS
# ======================================================================

def main() -> None:
    if not config.bot_token:
        log.critical("A DISCORD_BOT_TOKEN hiányzik a konfigurációból!")
        sys.exit(1)
    
    bot.run(config.bot_token)


if __name__ == "__main__":
    main()
