"""
NeonTiers Bot - Tier Utils (commands/tier_utils.py)
Segédfüggvények, kategória azonosítók és aktív várólisták kezelése.
"""

import discord
import time
import datetime

# Kategória azonosítók
MODERN_CATEGORY_ID = 1469766438238687496
LEGACY_CATEGORY_ID = 1520523939225276536

THEME_LIGHT_PURPLE = 0x9b59b6
THEME_LIGHT_BLUE = 0x3498db

HT_TICKETS_FILE = "ht_tickets.json"
ACTIVE_QUEUES = {}  # queue_ch_id: { "players": [...], "testers": [...], "gamemode": ..., "msg_id": ... }
VALID_HT_TIERS = ["HT1", "HT2", "HT3", "HT4", "HT5", "LT1", "LT2", "LT3", "LT4", "LT5"]
ALLOWED_QUEUE_TIERS = VALID_HT_TIERS

COOLDOWNS = {}  # (user_id, gamemode): timestamp

def get_ticket_category(guild: discord.Guild, is_legacy: bool):
    cat_id = LEGACY_CATEGORY_ID if is_legacy else MODERN_CATEGORY_ID
    return guild.get_channel(cat_id)

def check_timeout(user_id: int, gamemode: str):
    key = (user_id, gamemode)
    if key in COOLDOWNS:
        remaining = COOLDOWNS[key] - time.time()
        if remaining > 0:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            return True, f"{mins}p {secs}mp"
    return False, ""

def set_cooldown(user_id: int, gamemode: str, duration_seconds: int = 3600):
    COOLDOWNS[(user_id, gamemode)] = time.time() + duration_seconds

def get_cooldown(user_id: int, gamemode: str):
    return COOLDOWNS.get((user_id, gamemode), 0)

async def update_queue_message(message: discord.Message, q_data: dict, mode_key: str):
    players = q_data["players"]
    testers = q_data["testers"]
    
    players_text = ""
    if not players:
        players_text = "*- Üres -*"
    else:
        for i, p in enumerate(players, 1):
            players_text += f"`{i}.` <@{p['id']}> (**{p['mc']}**) - `{p['status']}`\n"

    testers_text = ""
    for t_id in testers:
        testers_text += f"🛡️ <@{t_id}>\n"
    if not testers_text:
        testers_text = "*- Nincs aktív teszter -*"

    desc = f"**Helyek:** {len(players)}/20\n\n**Játékosok a várólistán:**\n{players_text}\n**Aktív Teszterek:**\n{testers_text}"
    
    embed = message.embeds[0]
    embed.description = desc
    await message.edit(embed=embed)

async def save_test_result_supabase(player_user, player_mc, gamemode, tier, tester_user, interaction):
    pass
