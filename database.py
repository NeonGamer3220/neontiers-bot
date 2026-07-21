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

try:
    import asyncpg
except ImportError:
    asyncpg = None

from config import (
    SUPABASE_URL, SUPABASE_KEY, USE_SUPABASE_API, WEBSITE_URL, BOT_API_KEY,
    DATABASE_URL, SUPABASE_PG_URL, DATA_FILE, HTTP_TIMEOUT_SECONDS,
    LINK_CODE_LENGTH, LINK_CODE_EXPIRY_MINUTES, POINTS, ELO_MIN,
    ELO_MATCH_SCORE_PREFIX, ALL_TICKET_TYPES
)
from config import get_gamemode_display_name, get_elo_for_rank, normalize_gamemode

db_pool = None
supabase_headers: Dict[str, str] = {}

# Globális HTTP Session az "Unclosed connection" hibák ellen!
http_session: Optional[aiohttp.ClientSession] = None  

async def get_session() -> aiohttp.ClientSession:
    """Biztosítja, hogy mindig csak egyetlen, stabil kapcsolat éljen a Supabase felé."""
    global http_session
    if http_session is None or http_session.closed:
        connector = aiohttp.TCPConnector(limit=100, force_close=False)
        http_session = aiohttp.ClientSession(connector=connector)
    return http_session

def _auth_headers() -> Dict[str, str]:
    if not BOT_API_KEY: return {}
    return {"Authorization": f"Bearer {BOT_API_KEY}"}

async def init_db():
    global db_pool, supabase_headers
    
    # Session inicializálása
    await get_session()
    
    if USE_SUPABASE_API:
        supabase_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        print(f"Using Supabase REST API: {SUPABASE_URL}/rest/v1/")
        return

    DB_CONNECTION_STRING = DATABASE_URL or SUPABASE_PG_URL
    if not DB_CONNECTION_STRING: return
    try:
        connection_str = DB_CONNECTION_STRING
        if connection_str.startswith("postgresql://"):
            connection_str = connection_str.replace("postgresql://", "postgres://", 1)
        db_pool = await asyncpg.create_pool(connection_str, min_size=1, max_size=5)
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize database: {e}")

async def close_db():
    global db_pool, http_session
    if db_pool: await db_pool.close()
    if http_session and not http_session.closed:
        await http_session.close()

# ==========================================
# SUPABASE REST API METÓDUSOK
# ==========================================
async def supabase_select(table: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    if not USE_SUPABASE_API: return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"limit": "2000"}
    if filters:
        for key, value in filters.items(): 
            params[key] = f"eq.{value}"
    try:
        session = await get_session()
        async with session.get(url, headers=supabase_headers, params=params) as resp:
            if resp.status == 200: return await resp.json()
            return []
    except Exception: return []

async def supabase_insert(table: str, data: Dict[str, Any]) -> bool:
    if not USE_SUPABASE_API: return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        session = await get_session()
        async with session.post(url, headers=supabase_headers, json=data) as resp:
            if resp.status in (200, 201, 204): return True
            return False
    except Exception: return False

async def supabase_upsert(table: str, data: Dict[str, Any]) -> bool:
    if not USE_SUPABASE_API: return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = supabase_headers.copy()
    headers["Prefer"] = "resolution=merge-duplicates"
    try:
        session = await get_session()
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status in (200, 201, 204): return True
            return False
    except Exception: return False

async def supabase_update(table: str, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    if not USE_SUPABASE_API: return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    for key, value in filters.items(): params[key] = f"eq.{value}"
    try:
        session = await get_session()
        async with session.patch(url, headers=supabase_headers, json=data, params=params) as resp:
            if resp.status in (200, 204): return True
            return False
    except Exception: return False

async def supabase_delete(table: str, filters: Dict[str, Any]) -> bool:
    if not USE_SUPABASE_API: return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {}
    for key, value in filters.items(): params[key] = f"eq.{value}"
    try:
        session = await get_session()
        async with session.delete(url, headers=supabase_headers, params=params) as resp:
            if resp.status in (200, 204): return True
            return False
    except Exception: return False

# ==========================================
# SUPABASE ACTIVE MATCHES
# ==========================================
async def get_all_active_matches() -> List[Dict[str, Any]]:
    if not USE_SUPABASE_API: return []
    return await supabase_select("active_matches")

async def get_active_match(channel_id: int) -> Optional[dict]:
    if not USE_SUPABASE_API: return None
    results = await supabase_select("active_matches", {"channel_id": str(channel_id)})
    if results and len(results) > 0: return results[0].get("match_data")
    return None

async def set_active_match(channel_id: int, match_data: dict) -> bool:
    if not USE_SUPABASE_API: return False
    payload = {"channel_id": str(channel_id), "match_data": match_data}
    return await supabase_upsert("active_matches", payload)

async def delete_active_match(channel_id: int) -> bool:
    if not USE_SUPABASE_API: return False
    return await supabase_delete("active_matches", {"channel_id": str(channel_id)})

async def get_busy_players_for_mode(gamemode: str) -> Set[int]:
    busy_ids = set()
    if USE_SUPABASE_API:
        results = await supabase_select("active_matches")
        for row in results:
            match_data = row.get("match_data", {})
            if match_data.get("gamemode") == gamemode:
                p1 = match_data.get("player1_id")
                p2 = match_data.get("player2_id")
                if p1: busy_ids.add(int(p1))
                if p2: busy_ids.add(int(p2))
    return busy_ids

# ==========================================
# ELO RANG LEKÉRDEZÉSEK
# ==========================================
async def get_all_elos_for_mode_async(mode_key: str) -> List[Dict[str, Any]]:
    if USE_SUPABASE_API:
        mode_param = get_gamemode_display_name(mode_key).strip().lower()
        url = f"{SUPABASE_URL}/rest/v1/elos"
        params = {"limit": "2000"} 
        try:
            session = await get_session()
            async with session.get(url, headers=supabase_headers, params=params) as resp:
                if resp.status == 200:
                    all_data = await resp.json()
                    return [t for t in all_data if str(t.get("gamemode", "")).strip().lower() == mode_param]
        except: pass
    return []

async def get_player_elo_for_mode(username: str, mode_key: str) -> str:
    if USE_SUPABASE_API:
        all_elos = await get_all_elos_for_mode_async(mode_key)
        uname_target = username.strip().lower()
        
        for t in all_elos:
            if str(t.get("username", "")).strip().lower() == uname_target:
                return str(t.get("elo", "500"))
    return "500"

# ==========================================
# API EREDMÉNY MENTÉSE
# ==========================================
async def api_get_elos(username: str, mode: str) -> Dict[str, Any]:
    if not WEBSITE_URL: return {"status": 0, "data": {"elos": []}}
    url = f"{WEBSITE_URL}/api/elos"
    params = []
    if username: params.append(f"username={username}")
    if mode: params.append(f"gamemode={get_gamemode_display_name(mode)}")
    if params: url += "?" + "&".join(params)
    try:
        session = await get_session()
        async with session.get(url, headers=_auth_headers(), timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)) as resp:
            try: data = await resp.json()
            except: data = {"error": await resp.text()}
            return {"status": resp.status, "data": data}
    except: return {"status": 0, "data": {"elos": []}}

async def api_post_elo(username: str, mode: str, elo: Any, tester: discord.Member) -> Dict[str, Any]:
    mode_for_api = get_gamemode_display_name(mode)
    if USE_SUPABASE_API:
        points = 0
        try:
            elo_val = int(elo)
            if elo_val >= 1750: points = 10
            elif elo_val >= 1500: points = 6
            elif elo_val >= 1250: points = 4
            elif elo_val >= 1000: points = 3
            elif elo_val >= 750: points = 2
            elif elo_val >= 500: points = 1
        except: pass

        try: numeric_elo = int(elo)
        except: numeric_elo = 500

        payload = {
            "username": username, "gamemode": mode_for_api, 
            "elo": numeric_elo, "points": points,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        all_elos = await get_all_elos_for_mode_async(mode)
        uname_target = username.strip().lower()
        existing_id = None
        
        for t in all_elos:
            if str(t.get("username", "")).strip().lower() == uname_target:
                existing_id = t.get("id")
                break

        session = await get_session()
        if existing_id: 
            update_url = f"{SUPABASE_URL}/rest/v1/elos?id=eq.{existing_id}"
            await session.patch(update_url, headers=supabase_headers, json=payload)
        else: 
            url = f"{SUPABASE_URL}/rest/v1/elos"
            await session.post(url, headers=supabase_headers, json=payload)
                
        return {"status": 200, "save_ok": True}
    return {"status": 0, "save_ok": False}

async def api_rename_player(old_name: str, new_name: str) -> Dict[str, Any]:
    if USE_SUPABASE_API:
        await supabase_update("elos", {"username": new_name}, {"username": old_name})
        await supabase_update("linked_accounts", {"minecraft_name": new_name}, {"minecraft_name": old_name})
        return {"status": 200}
    return {"status": 400}

async def api_set_ban(username: str, banned: bool, expires_at: Optional[int] = None, reason: str = "") -> Dict[str, Any]:
    return {"status": 200}

async def api_remove_player(username: str, gamemode: Optional[str] = None) -> Dict[str, Any]:
    if USE_SUPABASE_API:
        await supabase_delete("elos", {"username": username})
        return {"status": 200, "data": {"modes": "All"}}
    return {"status": 400}

# ==========================================
# MINECRAFT LINK RENDSZER (ÚJRAÍRVA: INSTANT ELO GENERÁLÁS!)
# ==========================================
async def get_linked_minecraft_name_async(discord_id: int) -> Optional[str]:
    if USE_SUPABASE_API:
        results = await supabase_select("linked_accounts", {"discord_id": str(discord_id)})
        if results: return results[0]['minecraft_name']
    data = _load_link_data()
    return data.get(str(discord_id))

async def link_minecraft_account_async(discord_id: int, minecraft_name: str) -> bool:
    if USE_SUPABASE_API:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload = {
            "discord_id": str(discord_id), 
            "minecraft_name": minecraft_name,
            "linked_at": now
        }
        success = await supabase_upsert("linked_accounts", payload)
        
        # HA SIKERES VOLT A LINKELÉS, AZONNAL GENERÁLJUK A 500 ELO SORAIT AZ ÖSSZES JÁTÉKMÓDHOZ!
        if success:
            session = await get_session()
            
            # Először megnézzük, van-e már valamilyen ELO sora (hogy ne duplikáljunk újra-linkelésnél)
            url_get = f"{SUPABASE_URL}/rest/v1/elos"
            params = {"select": "gamemode", "username": f"eq.{minecraft_name}"}
            existing_modes = []
            try:
                async with session.get(url_get, headers=supabase_headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        existing_modes = [str(r.get("gamemode", "")).strip().lower() for r in data]
            except: pass

            url_post = f"{SUPABASE_URL}/rest/v1/elos"
            # Végigmegyünk az összes Modern és Legacy módon a configból
            for label, mode_key, _ in ALL_TICKET_TYPES:
                mode_display = get_gamemode_display_name(mode_key)
                
                # Csak akkor szúrjuk be, ha még nem létezett az adott játékmód
                if mode_display.strip().lower() not in existing_modes:
                    elo_payload = {
                        "username": minecraft_name,
                        "gamemode": mode_display,
                        "elo": 500,
                        "points": 1,
                        "created_at": now
                    }
                    try:
                        await session.post(url_post, headers=supabase_headers, json=elo_payload)
                    except: pass
                    
        return success
        
    data = _load_link_data()
    data[str(discord_id)] = minecraft_name
    _save_link_data(data)
    return True

async def unlink_minecraft_account_async(discord_id: int) -> bool:
    if USE_SUPABASE_API:
        return await supabase_delete("linked_accounts", {"discord_id": str(discord_id)})
    return False

async def get_discord_by_minecraft_async(minecraft_name: str) -> Optional[int]:
    if USE_SUPABASE_API:
        all_links = await supabase_select("linked_accounts")
        for link in all_links:
            if str(link.get("minecraft_name", "")).strip().lower() == minecraft_name.strip().lower():
                return int(link["discord_id"])
    return None

async def get_all_linked_accounts_async() -> Dict[str, int]:
    if USE_SUPABASE_API:
        results = await supabase_select("linked_accounts")
        if results:
            return {str(row['minecraft_name']).strip().lower(): int(row['discord_id']) for row in results}
    
    data = _load_link_data()
    return {v.lower(): int(k) for k, v in data.items()}

def get_linked_minecraft_name(discord_id: int) -> Optional[str]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(get_linked_minecraft_name_async(discord_id), loop).result()
        else:
            return asyncio.run(get_linked_minecraft_name_async(discord_id))
    except:
        return None

def unlink_minecraft_account(discord_id: int) -> bool:
    return asyncio.run(unlink_minecraft_account_async(discord_id))

# ==========================================
# PENDING LINK CODES
# ==========================================
async def generate_link_code_async(discord_id: int) -> Optional[str]:
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    if USE_SUPABASE_API:
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(minutes=10)
        
        payload = {
            "discord_id": str(discord_id),
            "code": code,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "used": False
        }
        
        success = await supabase_insert("pending_codes", payload)
        if success:
            return code
        return None
        
    data = _load_pending_link_codes()
    data[code] = {"discord_id": discord_id, "expires_at": time.time() + (10 * 60)}
    _save_pending_link_codes(data)
    return code

async def verify_link_code_async(code: str) -> Optional[int]:
    data = _load_pending_link_codes()
    code_info = data.get(code.upper())
    if not code_info or time.time() > code_info.get("expires_at", 0): return None
    discord_id = code_info.get("discord_id")
    data.pop(code.upper(), None)
    _save_pending_link_codes(data)
    return discord_id

async def get_pending_link_code_async(discord_id: int) -> Optional[str]:
    data = _load_pending_link_codes()
    for code, info in data.items():
        if info.get("discord_id") == discord_id and time.time() < info.get("expires_at", 0): return code
    return None

async def validate_link_code_for_user(discord_id: int, code: str) -> bool:
    data = _load_pending_link_codes()
    info = data.get(code.upper())
    if info and info.get("discord_id") == discord_id and time.time() < info.get("expires_at", 0): return True
    return False

def is_player_banned(username: str) -> bool:
    data = _load_ban_data()
    return username.lower() in data

def get_ban_info(username: str) -> Optional[Dict[str, Any]]:
    data = _load_ban_data()
    return data.get(username.lower())

def ban_player(username: str, days: int, reason: str = "") -> None:
    data = _load_ban_data()
    data[username.lower()] = {"reason": reason, "expires_at": time.time() + (days * 86400) if days > 0 else 0}
    _save_ban_data(data)

def unban_player(username: str) -> bool:
    data = _load_ban_data()
    if username.lower() in data:
        data.pop(username.lower())
        _save_ban_data(data)
        return True
    return False

def _load_link_data():
    if not os.path.exists("links.json"): return {}
    with open("links.json", "r") as f: return json.load(f)
def _save_link_data(d):
    with open("links.json", "w") as f: json.dump(d, f)
def _load_pending_link_codes():
    if not os.path.exists("pending_links.json"): return {}
    with open("pending_links.json", "r") as f: return json.load(f)
def _save_pending_link_codes(d):
    with open("pending_links.json", "w") as f: json.dump(d, f)
def _load_ban_data():
    if not os.path.exists("bans.json"): return {}
    with open("bans.json", "r") as f: return json.load(f)
def _save_ban_data(d):
    with open("bans.json", "w") as f: json.dump(d, f)

async def get_tgf_cooldown(discord_id: int) -> Optional[datetime.datetime]:
    if USE_SUPABASE_API:
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
    if USE_SUPABASE_API:
        expires_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        payload = {
            "discord_id": str(discord_id),
            "expires_at": expires_dt.isoformat()
        }
        return await supabase_upsert("tgf_cooldowns", payload)
    return False