"""
NeonTiers Bot - Config Modul
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_int(env_name: str, default: int) -> int:
    val = os.getenv(env_name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


# ======================================================================
# KONSTANSOK A REGI ÉS ÚJ PARANCSOKNAK
# ======================================================================

TIER_RESULTS_CHANNEL_ID = _get_int("TIER_RESULTS_CHANNEL_ID", 0)
STAFF_ROLE_ID = _get_int("STAFF_ROLE_ID", 0)
BANNED_ROLE_ID = _get_int("BANNED_ROLE_ID", 0)
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://neontiers.hu")
MODE_LIST = ["HT", "LT", "TEST"]  # Igazítsd a saját játékmódjaidhoz!


@dataclass
class Config:
    bot_token: str = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN", "")
    guild_id: int = _get_int("GUILD_ID", 123456789012345678)
    ticket_category_id: int = _get_int("TICKET_CATEGORY_ID", 0)
    results_channel_id: int = _get_int("RESULTS_CHANNEL_ID", 0)
    regulator_role_id: int = _get_int("REGULATOR_ROLE_ID", 0)
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    auto_start_poll_seconds: int = _get_int("AUTO_START_POLL_SECONDS", 30)


config = Config()
