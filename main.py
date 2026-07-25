"""
NeonTiers Bot - Main Entry Point (main.py)
"""

import asyncio
import logging
import os
import sys
import discord
from discord.ext import commands

from config import config

# Logging beállítása
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("neontiers.main")

# Betöltendő cogs/extenziók listája (commands.panels ELTÁVOLÍTVA)
INITIAL_EXTENSIONS = [
    "commands.profile",
    "commands.linking",
    "commands.tgf",
    "commands.tier_system",
    "commands.staff",
    "commands.ban_enforcement",
    "commands.spin",
    "commands.support_ticket",
    "commands.notifications",
    "commands.weekly_report",
    "commands.regulator_panel",
    "commands.send_message",
    "commands.queue_panel", # <--- EZT ADD HOZZÁ
]

# Discord Bot Intents beállítása
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    log.info("Fő bot elindult: %s (ID: %s)", bot.user, bot.user.id)
    
    try:
        # 1. Megtisztítjuk az esetleges szerver-szintű (Guild) parancsduplázódásokat
        for guild in bot.guilds:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        
        # 2. Szinkronizáljuk a globális parancsokat
        synced = await bot.tree.sync()
        log.info("Sikeresen megtisztítva és szinkronizálva %d globális parancs.", len(synced))
    except Exception as exc:
        log.error("Hiba a parancsok szinkronizálásakor: %s", exc)


async def main():
    async with bot:
        # Cogs betöltése
        for ext in INITIAL_EXTENSIONS:
            try:
                await bot.load_extension(ext)
                log.info("Sikeresen betöltve az extenzió: %s", ext)
            except Exception as exc:
                log.error("Hiba a(z) %s extenzió betöltésekor: %s", ext, exc)

        # Bot indítása a token használatával
        token = os.getenv("DISCORD_TOKEN") or getattr(config, "DISCORD_TOKEN", None)
        if not token:
            log.critical("Nincs beállítva DISCORD_TOKEN a környezeti változók között!")
            return

        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot leállítva a felhasználó által.")
