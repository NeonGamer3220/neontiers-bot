"""
NeonTiers Bot - Config Modul
Környezeti változók és konfigurációs beállítások kezelése.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .env fájl betöltése (ha létezik helyileg)
load_dotenv()


def _get_int(env_name: str, default: int) -> int:
    val = os.getenv(env_name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass
class Config:
    # Discord Bot Token
    bot_token: str = os.getenv("DISCORD_BOT_TOKEN", "")

    # Szerver és Csatorna ID-k (cseréld ki a sajátjaidra, ha nincsenek .env-ben)
    guild_id: int = _get_int("GUILD_ID", 123456789012345678)
    ticket_category_id: int = _get_int("TICKET_CATEGORY_ID", 0)
    results_channel_id: int = _get_int("RESULTS_CHANNEL_ID", 0)
    regulator_role_id: int = _get_int("REGULATOR_ROLE_ID", 0)

    # Supabase Adatbázis Beállítások
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    # Időzítők / Ciklusok (Másodpercben)
    auto_start_poll_seconds: int = _get_int("AUTO_START_POLL_SECONDS", 30)


# ======================================================================
# EZ A SOR HIÁNYZOTT: Létrehozzuk a 'config' kisbetűs példányt!
# ======================================================================
config = Config()
