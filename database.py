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
# MINECRAFT LINKELÉS (linked_accounts & pending_codes)
# ==========================================
async def get_linked_minecraft_name_async(discord_id: int) -> Optional[str]:
    if USE_SUPABASE_API:
        results = await supabase_select("linked_accounts", {"discord_id": str(discord_id)})
        if results and len(results) > 0:
            return results[0].get("minecraft_name")
    return None

async def get_discord_by_minecraft_async(minecraft_name: str) -> Optional[int]:
    if USE_SUPABASE_API:
        results = await supabase_select("linked_accounts", {"minecraft_name": minecraft_name})
        if results and len(results) > 0:
            d_id = results[0].get("discord_id")
            return int(d_id) if d_id else None
    return None

async def unlink_minecraft_account_async(discord_id: int) -> bool:
    if USE_SUPABASE_API:
        return await supabase_delete("linked_accounts", {"discord_id": str(discord_id)})
    return False

def _generate_random_code(length: int = LINK_CODE_LENGTH) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

async def generate_link_code_async(discord_id: int) -> Optional[str]:
    """Generates a link code for /link and saves it to pending_codes."""
    code = _generate_random_code()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LINK_CODE_EXPIRY_MINUTES)
    
    if USE_SUPABASE_API:
        # Töröljük a korábbi ideiglenes kódokat erről a discord id-ról
        await supabase_delete("pending_codes", {"discord_id": str(discord_id)})
        
        success = await supabase_insert("pending_codes", {
            "code": code,
            "discord_id": str(discord_id),
            "expires_at": expires_at.isoformat()
        })
        if success:
            return code
    return None

# Sync verziók visszafelé kompatibilitás miatt
def get_linked_minecraft_name(discord_id: int) -> Optional[str]:
    try:
        return asyncio.run(get_linked_minecraft_name_async(discord_id))
    except Exception:
        return None

# ==========================================
# TGF COOLDOWN SYSTEM
# ==========================================
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
    
def create_pending_invite(self, discord_id: int, invite_type: str, ticket_channel_id: int) -> dict:
        resp = self._client.table("pending_invites").insert({
            "discord_id": discord_id,
            "invite_type": invite_type,
            "ticket_channel_id": ticket_channel_id
        }).execute()
        return resp.data[0] if resp.data else {}

    def get_pending_invite_for_user(self, discord_id: int) -> list[dict]:
        resp = self._client.table("pending_invites").select("*").eq("discord_id", discord_id).eq("completed", False).execute()
        return resp.data or []

    def mark_invite_completed(self, invite_id: str) -> None:
        self._client.table("pending_invites").update({"completed": True}).eq("id", invite_id).execute()

    def get_due_reminders(self) -> list[dict]:
        # 24 óránál régebbi, még nem emlékeztetett és nem befejezett 'magas' típusú meghívók
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        resp = self._client.table("pending_invites").select("*") \
            .eq("invite_type", "magas") \
            .eq("reminder_sent", False) \
            .eq("completed", False) \
            .lte("created_at", cutoff.isoformat()) \
            .execute()
        return resp.data or []

    def mark_reminder_sent(self, invite_id: str) -> None:
        self._client.table("pending_invites").update({"reminder_sent": True}).eq("id", invite_id).execute()
