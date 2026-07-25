import os
import json
import time
import datetime
import aiohttp
import discord
from typing import Optional

from config import (
    ALL_TICKET_TYPES, LEGACY_TICKET_TYPES, ELO_TICKET_CATEGORY_ID,
    LEGACY_TICKET_CATEGORY_ID, get_gamemode_display_name,
    SUPABASE_URL, SUPABASE_KEY
)

# ==========================================
# DESIGN TÉMA SZÍNEK
# ==========================================
THEME_LIGHT_PURPLE = 0xA388EE
THEME_LIGHT_BLUE = 0x88CCEE

# ==========================================
# ADATTÁROLÓK & CONSTANSOK
# ==========================================
COOLDOWN_FILE = "tier_cooldowns.json"
HT_TICKETS_FILE = "ht_tickets.json"
ACTIVE_QUEUES = {} 

MODE_COLORS = {
    "vanilla": 0x55FF55, "uhc": 0xFFAA00, "pot": 0xFF5555, "nethpot": 0xAA0000,
    "smp": 0x55FFFF, "sword": 0xAAAAAA, "axe": 0xAAAAAA, "mace": 0xAA00AA,
    "cart": 0xAAAAAA, "creeper": 0x55FF55, "diasmp": 0x55FFFF, "ogvanilla": 0x55FF55,
    "shieldlessuhc": 0xFFAA00, "spearmace": 0xAA00AA, "spearelytra": 0xAA00AA,
    "stickfight": 0xAA5500, "trident": 0x55FFFF, "boxing": 0x5555FF, "combo": 0xFF5555,
    "bridge": 0x55FFFF, "nodebuff": 0xFF5555, "op": 0x55FFFF, "soup": 0xAA5500,
    "fireballfight": 0xFFAA00
}

VALID_HT_TIERS = ["LT3", "HT3", "LT2", "HT2", "LT1", "HT1", "RLT2", "RHT2", "RLT1", "RHT1"]
ALLOWED_QUEUE_TIERS = ["UNRANKED", "LT5", "HT5", "LT4", "HT4", "LT3"]

# ==========================================
# SUPABASE HELPER MŰVELETEK
# ==========================================
async def save_test_result_supabase(username: str, gamemode_display: str, rank: str, points: int, existing_id: Optional[int] = None):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    payload = {
        "username": username,
        "gamemode": gamemode_display,
        "rank": rank,
        "points": points,
        "created_at": now
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            if existing_id:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests?id=eq.{existing_id}"
                async with session.patch(url, headers=headers, json=payload):
                    pass
            else:
                url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests"
                async with session.post(url, headers=headers, json=payload):
                    pass
    except Exception as e:
        print(f"[ERROR] Supabase mentési hiba: {e}")

# ==========================================
# SEGÉDFÜGGVÉNYEK
# ==========================================
def get_cooldown(discord_id: int, gamemode: str) -> float:
    if not os.path.exists(COOLDOWN_FILE): return 0
    try:
        with open(COOLDOWN_FILE, "r") as f:
            return json.load(f).get(str(discord_id), {}).get(gamemode, 0)
    except: return 0

def set_cooldown(discord_id: int, gamemode: str):
    data = {}
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, "r") as f: data = json.load(f)
        except: pass
    if str(discord_id) not in data: data[str(discord_id)] = {}
    data[str(discord_id)][gamemode] = time.time() + (14 * 24 * 3600)
    with open(COOLDOWN_FILE, "w") as f: json.dump(data, f)

def check_timeout(discord_id: int) -> bool:
    if not os.path.exists("timeouts.json"): return False
    try:
        with open("timeouts.json", "r") as f:
            data = json.load(f).get(str(discord_id))
            if data and time.time() < data.get("expires_at", 0): return True
    except: pass
    return False

def get_ticket_category(guild: discord.Guild, mode_key: str) -> Optional[discord.CategoryChannel]:
    is_legacy = any(k == mode_key for _, k, _ in LEGACY_TICKET_TYPES)
    cat_id = LEGACY_TICKET_CATEGORY_ID if is_legacy else ELO_TICKET_CATEGORY_ID
    category = guild.get_channel(cat_id) if cat_id else None
    if isinstance(category, discord.CategoryChannel):
        return category
    return None

async def update_queue_message(message: discord.Message, q_data: dict, gamemode: str):
    emoji_str = "🎮"
    label_name = get_gamemode_display_name(gamemode)
    
    for lbl, key, em_raw in ALL_TICKET_TYPES:
        if key == gamemode:
            emoji_str = str(em_raw)
            if emoji_str.isdigit():
                safe_name = lbl.replace(" ", "").replace("-", "")
                emoji_str = f"<:{safe_name}:{emoji_str}>"
            break
            
    desc = f"**Helyek:** {len(q_data['players'])}/20\n\n**Játékosok a várólistán:**\n"
    if not q_data["players"]:
        desc += "*- Üres -*\n"
    else:
        found_kov = False
        for p in q_data["players"]:
            disp_status = p["status"]
            if disp_status == "VÁR" and not found_kov:
                disp_status = "KÖV"
                found_kov = True
            desc += f"`{disp_status}` <@{p['id']}> ({p['mc']})\n"
            
    desc += "\n**Aktív Teszterek:**\n"
    if not q_data["testers"]:
        desc += "*- Nincs teszter -*\n"
    for t_id in q_data["testers"]:
        desc += f"🛡️ <@{t_id}>\n"
        
    embed = discord.Embed(
        title=f"{emoji_str} {label_name} Várólista", 
        description=desc, 
        color=discord.Color(THEME_LIGHT_BLUE)
    )
    try:
        await message.edit(embed=embed)
    except: pass
