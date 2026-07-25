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
    SUPABASE_URL, SUPABASE_KEY, MODERN_RESULT_CHANNEL_ID, LEGACY_RESULT_CHANNEL_ID
)

# =========================================
# DESIGN TÉMA SZÍNEK
# =========================================
THEME_LIGHT_PURPLE = 0xA388EE
THEME_LIGHT_BLUE = 0x88CCEE

# =========================================
# ADATTÁROLÓK & CONSTANSOK
# =========================================
COOLDOWN_FILE = "tier_cooldowns.json"
HT_TICKETS_FILE = "ht_tickets.json"
ACTIVE_QUEUES = {}  # channel_id -> queue data

MODE_COLORS = {
    "vanilla": 0x55FF55, "uhc": 0xFFAA00, "pot": 0xFF5555, "nethpot": 0xAA0000,
    "smp": 0x55FFFF, "sword": 0xAAAAAA, "axe": 0xAAAAAA, "mace": 0xAA00AA,
    "cart": 0xAAAAAA, "creeper": 0x55FF55, "diasmp": 0x55FFFF, "ogvanilla": 0x55FF55,
    "shieldlessuhc": 0xFFAA00, "spearmace": 0xAA00AA, "spearelytra": 0x55FFFF, "trident": 0x55FFFF
}

VALID_HT_TIERS = ["HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "UNRANKED"]
ALLOWED_QUEUE_TIERS = ["HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "Unranked"]

# =========================================
# COOLDOWN KEZELÉS (JSON)
# =========================================
def load_cooldowns() -> dict:
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cooldowns(data: dict):
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[COOLDOWN SAVE ERROR] {e}")

def get_cooldown(user_id: int, gamemode: str) -> float:
    cd = load_cooldowns()
    return cd.get(str(user_id), {}).get(gamemode.lower(), 0.0)

def set_cooldown(user_id: int, gamemode: str, timestamp: float):
    cd = load_cooldowns()
    u_str = str(user_id)
    if u_str not in cd:
        cd[u_str] = {}
    cd[u_str][gamemode.lower()] = timestamp
    save_cooldowns(cd)

def check_timeout(user_id: int, gamemode: str, cooldown_days: int = 14) -> tuple[bool, str]:
    last_time = get_cooldown(user_id, gamemode)
    if not last_time:
        return False, ""
    
    cooldown_seconds = cooldown_days * 86400
    elapsed = time.time() - last_time
    if elapsed < cooldown_seconds:
        remaining = cooldown_seconds - elapsed
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        minutes = int((remaining % 3600) // 60)
        return True, f"{days} nap, {hours} óra, {minutes} perc"
    return False, ""

# =========================================
# SUPABASE EREDMÉNY MENTÉS & BEJELENTÉSEK
# =========================================
async def save_test_result_supabase(
    discord_user: discord.User,
    minecraft_name: str,
    gamemode: str,
    tier: str,
    tester: discord.User,
    interaction: discord.Interaction
):
    # Supabase API hívás (tests tábla)
    if SUPABASE_URL and SUPABASE_KEY:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/tests"
        payload = {
            "discord_id": str(discord_user.id),
            "username": minecraft_name,
            "gamemode": gamemode,
            "rank": tier,
            "tester": tester.display_name,
            "tester_id": str(tester.id),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status not in (200, 201, 204):
                        err = await resp.text()
                        print(f"[SUPABASE SAVE ERROR] {resp.status}: {err}")
        except Exception as e:
            print(f"[SUPABASE EXCEPTION] {e}")

    # Eredmény csatornákra küldés
    if MODERN_RESULT_CHANNEL_ID:
        try:
            channel = interaction.client.get_channel(MODERN_RESULT_CHANNEL_ID) or await interaction.client.fetch_channel(MODERN_RESULT_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="🏆 Új Tier Teszt Eredmény", 
                    color=discord.Color.blue(), 
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Játékos", value=f"`{minecraft_name}` ({discord_user.mention})", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{tier}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Official Tiers")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[MODERN RESULT ERROR] {e}")

    if LEGACY_RESULT_CHANNEL_ID:
        try:
            channel = interaction.client.get_channel(LEGACY_RESULT_CHANNEL_ID) or await interaction.client.fetch_channel(LEGACY_RESULT_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="🏆 Új Tier Teszt Eredmény (Legacy)", 
                    color=discord.Color.dark_blue(), 
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Játékos", value=f"`{minecraft_name}` ({discord_user.mention})", inline=True)
                embed.add_field(name="Játékmód", value=f"`{gamemode}`", inline=True)
                embed.add_field(name="Elért Rank", value=f"**{tier}**", inline=True)
                embed.add_field(name="Teszter", value=tester.mention, inline=False)
                embed.set_footer(text="NeoTiers Legacy Tiers")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[LEGACY RESULT ERROR] {e}")

def get_ticket_category(guild: discord.Guild, is_legacy: bool = False) -> Optional[discord.CategoryChannel]:
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
        desc += "*- Nincs aktív teszter -\n"
    else:
        for t_id in q_data["testers"]:
            desc += f"🛡️ <@{t_id}>\n"
            
    embed = discord.Embed(title=f"{emoji_str} {label_name} Várólista", description=desc, color=discord.Color(THEME_LIGHT_BLUE))
    try:
        await message.edit(embed=embed)
    except Exception as e:
        print(f"[UPDATE QUEUE ERROR] {e}")
