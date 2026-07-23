import discord
import os
import json
import time
import asyncio
import datetime
import random
import string
from typing import Dict, Any, Optional, List, Set
import aiohttp

from config import (
    SUPABASE_URL, SUPABASE_KEY, USE_SUPABASE_API, WEBSITE_URL, BOT_API_KEY,
    HTTP_TIMEOUT_SECONDS, LINK_CODE_LENGTH, LINK_CODE_EXPIRY_MINUTES,
    normalize_gamemode, get_gamemode_display_name
)

# Globális HTTP Session az "Unclosed connection" hibák ellen
http_session: Optional[aiohttp.ClientSession] = None  

async def get_session() -> aiohttp.ClientSession:
    global http_session
    if http_session is None or http_session.closed:
        connector = aiohttp.TCPConnector(limit=100, force_close=False)
        http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        )
    return http_session

def supabase_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

async def init_db():
    print("[DATABASE] Adatbázis modul inicializálva.")

async def close_db():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()
        print("[DATABASE] HTTP session lezárva.")

# ==========================================
# OPTIMALIZÁLT SUPABASE API FUNKCIÓK
# ==========================================
async def supabase_select(table: str, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[DATABASE ERROR] Supabase URL vagy KEY hiányzik.")
        return []

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    if filters:
        for k, v in filters.items():
            params[k] = f"eq.{v}"

    session = await get_session()
    try:
        async with session.get(url, headers=supabase_headers(), params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                err_body = await resp.text()
                print(f"[SUPABASE SELECT ERROR] {resp.status} - {err_body}")
                return []
    except Exception as e:
        print(f"[SUPABASE SELECT EXCEPTION] {e}")
        return []

async def supabase_insert(table: str, data: Dict[str, Any]) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    session = await get_session()
    try:
        async with session.post(url, headers=supabase_headers(), json=data) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        print(f"[SUPABASE INSERT ERROR] {e}")
        return False

async def supabase_update(table: str, filters: Dict[str, str], data: Dict[str, Any]) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {k: f"eq.{v}" for k, v in filters.items()}
    session = await get_session()
    try:
        async with session.patch(url, headers=supabase_headers(), params=params, json=data) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[SUPABASE UPDATE ERROR] {e}")
        return False

async def supabase_delete(table: str, filters: Dict[str, str]) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {k: f"eq.{v}" for k, v in filters.items()}
    session = await get_session()
    try:
        async with session.delete(url, headers=supabase_headers(), params=params) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[SUPABASE DELETE ERROR] {e}")
        return False

# ==========================================
# INSTANT UPSERT ELO RÖGZÍTÉS
# ==========================================
async def api_post_elo_instant(username: str, mode: str, elo: str, tester: str) -> bool:
    """
    Instant Eredmény Rögzítés (Upsert):
    Egyetlen REST API kéréssel beszúrja vagy azonnal frissíti a játékos Tier-jét.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    url = f"{SUPABASE_URL}/rest/v1/tests"
    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    payload = {
        "username": username,
        "gamemode": mode,
        "rank": elo,
        "tester": tester,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    session = await get_session()
    try:
        async with session.post(url, headers=headers, json=payload, params={"on_conflict": "username,gamemode"}) as resp:
            return resp.status in (200, 201, 204)
    except Exception as e:
        print(f"[INSTANT ELO POST ERROR] {e}")
        return False

# ==========================================
# MINECRAFT LINKELÉS ÉS TGF COOLDOWN
# ==========================================
async def get_linked_minecraft_name_async(discord_id: int) -> Optional[str]:
    results = await supabase_select("user_links", {"discord_id": str(discord_id)})
    if results:
        return results[0].get("minecraft_name")
    return None

async def get_discord_by_minecraft_async(mc_name: str) -> Optional[int]:
    results = await supabase_select("user_links", {"minecraft_name": mc_name})
    if results:
        try:
            return int(results[0].get("discord_id"))
        except (ValueError, TypeError):
            return None
    return None

async def generate_link_code_async(discord_id: int) -> Optional[str]:
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=LINK_CODE_LENGTH))
    expires_at = time.time() + (LINK_CODE_EXPIRY_MINUTES * 60)
    
    await supabase_delete("pending_links", {"discord_id": str(discord_id)})
    
    success = await supabase_insert("pending_links", {
        "code": code,
        "discord_id": str(discord_id),
        "expires_at": expires_at
    })
    return code if success else None

async def unlink_minecraft_account_async(discord_id: int) -> bool:
    return await supabase_delete("user_links", {"discord_id": str(discord_id)})

async def get_tgf_cooldown(discord_id: int) -> Optional[datetime.datetime]:
    results = await supabase_select("tgf_cooldowns", {"discord_id": str(discord_id)})
    if results and len(results) > 0:
        expires_str = results[0].get("expires_at")
        if expires_str:
            expires_dt = datetime.datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) < expires_dt:
                return expires_dt
            else:
                await supabase_delete("tgf_cooldowns", {"discord_id": str(discord_id)})
    return None

async def set_tgf_cooldown(discord_id: int, days: int = 30) -> bool:
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    await supabase_delete("tgf_cooldowns", {"discord_id": str(discord_id)})
    return await supabase_insert("tgf_cooldowns", {
        "discord_id": str(discord_id),
        "expires_at": expires_at.isoformat()
    })
