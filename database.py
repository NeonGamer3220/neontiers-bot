"""
NeonTiers Bot - Database Modul
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, TypeVar

from supabase import Client, create_client
from config import config

log = logging.getLogger("neontiers.database")

T = TypeVar("T")


async def arun(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


class Database:
    def __init__(self) -> None:
        self._client: Client | None = None
        self._init_client()

    def _init_client(self) -> None:
        if config.supabase_url and config.supabase_key:
            try:
                self._client = create_client(config.supabase_url, config.supabase_key)
                log.info("Supabase adatbázis kapcsolat sikeresen kiépítve.")
            except Exception as exc:
                log.error("Hiba a Supabase kliens létrehozásakor: %s", exc)
                self._client = None
        else:
            log.warning("Supabase URL vagy Key hiányzik a konfigurációból!")

    # --- Összekapcsolt fiókok ---
    def get_linked_account(self, discord_id: int) -> dict | None:
        if not self._client:
            return None
        resp = self._client.table("linked_accounts").select("*").eq("discord_id", discord_id).execute()
        return resp.data[0] if resp.data else None

    def link_account(self, discord_id: int, minecraft_name: str, uuid: str = "") -> dict:
        if not self._client:
            return {}
        data = {
            "discord_id": discord_id,
            "minecraft_name": minecraft_name,
            "uuid": uuid,
            "linked_at": datetime.now(timezone.utc).isoformat()
        }
        resp = self._client.table("linked_accounts").upsert(data, on_conflict="discord_id").execute()
        return resp.data[0] if resp.data else {}

    def unlink_account(self, discord_id: int) -> bool:
        if not self._client:
            return False
        resp = self._client.table("linked_accounts").delete().eq("discord_id", discord_id).execute()
        return bool(resp.data)

    # --- Bajnokságok & Meccsek ---
    def create_tournament(self, name: str, end_time: datetime, queue_message_id: int, guild_id: int, ticket_category_id: int, results_channel_id: int, regulator_role_id: int) -> dict:
        if not self._client:
            return {}
        data = {
            "name": name,
            "status": "pending",
            "end_time": end_time.isoformat(),
            "queue_message_id": queue_message_id,
            "guild_id": guild_id,
            "ticket_category_id": ticket_category_id,
            "results_channel_id": results_channel_id,
            "regulator_role_id": regulator_role_id,
            "current_round": 0
        }
        resp = self._client.table("tournaments").insert(data).execute()
        return resp.data[0] if resp.data else {}

    def get_tournament(self, tournament_id: str) -> dict | None:
        if not self._client:
            return None
        resp = self._client.table("tournaments").select("*").eq("id", tournament_id).execute()
        return resp.data[0] if resp.data else None

    def update_tournament(self, tournament_id: str, **kwargs: Any) -> dict:
        if not self._client:
            return {}
        resp = self._client.table("tournaments").update(kwargs).eq("id", tournament_id).execute()
        return resp.data[0] if resp.data else {}

    def list_pending_tournaments(self) -> list[dict]:
        if not self._client:
            return []
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = self._client.table("tournaments").select("*").eq("status", "pending").lte("end_time", now_iso).execute()
        return resp.data or []

    def add_tournament_player(self, tournament_id: str, discord_id: int, minecraft_name: str) -> dict:
        if not self._client:
            return {}
        data = {"tournament_id": tournament_id, "discord_id": discord_id, "minecraft_name": minecraft_name}
        resp = self._client.table("tournament_players").upsert(data, on_conflict="tournament_id,discord_id").execute()
        return resp.data[0] if resp.data else {}

    def get_tournament_players(self, tournament_id: str) -> list[dict]:
        if not self._client:
            return []
        resp = self._client.table("tournament_players").select("*").eq("tournament_id", tournament_id).execute()
        return resp.data or []

    def create_match(self, tournament_id: str, round_number: int, player1_discord_id: int, player2_discord_id: int, player1_mc: str, player2_mc: str, ticket_channel_id: int) -> dict:
        if not self._client:
            return {}
        data = {
            "tournament_id": tournament_id,
            "round_number": round_number,
            "player1_discord_id": player1_discord_id,
            "player2_discord_id": player2_discord_id,
            "player1_mc": player1_mc,
            "player2_mc": player2_mc,
            "ticket_channel_id": ticket_channel_id,
            "winner_discord_id": None
        }
        resp = self._client.table("matches").insert(data).execute()
        return resp.data[0] if resp.data else {}

    def get_unresolved_matches(self, tournament_id: str) -> list[dict]:
        if not self._client:
            return []
        resp = self._client.table("matches").select("*").eq("tournament_id", tournament_id).is_("winner_discord_id", "null").execute()
        return resp.data or []

    def set_match_winner(self, match_id: str, winner_discord_id: int) -> dict:
        if not self._client:
            return {}
        resp = self._client.table("matches").update({"winner_discord_id": winner_discord_id}).eq("id", match_id).execute()
        return resp.data[0] if resp.data else {}

    # --- Invite rendszer ---
    def create_pending_invite(self, discord_id: int, invite_type: str, ticket_channel_id: int) -> dict:
        if not self._client:
            return {}
        data = {"discord_id": discord_id, "invite_type": invite_type, "ticket_channel_id": ticket_channel_id}
        resp = self._client.table("pending_invites").insert(data).execute()
        return resp.data[0] if resp.data else {}

    def get_pending_invite_for_user(self, discord_id: int) -> list[dict]:
        if not self._client:
            return []
        resp = self._client.table("pending_invites").select("*").eq("discord_id", discord_id).eq("completed", False).execute()
        return resp.data or []

    def mark_invite_completed(self, invite_id: str) -> None:
        if not self._client:
            return
        self._client.table("pending_invites").update({"completed": True}).eq("id", invite_id).execute()

    def get_due_reminders(self) -> list[dict]:
        if not self._client:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        resp = self._client.table("pending_invites").select("*") \
            .eq("invite_type", "magas") \
            .eq("reminder_sent", False) \
            .eq("completed", False) \
            .lte("created_at", cutoff.isoformat()) \
            .execute()
        return resp.data or []

    def mark_reminder_sent(self, invite_id: str) -> None:
        if not self._client:
            return
        self._client.table("pending_invites").update({"reminder_sent": True}).eq("id", invite_id).execute()


db = Database()

# ======================================================================
# BAZIKUS KOMPATIBILITÁSI FÜGGVÉNYEK A MEG LÉVŐ COG-OKNAK
# ======================================================================

def supabase_select(table: str, match_column: str, match_value: Any) -> list[dict]:
    if not db._client:
        return []
    resp = db._client.table(table).select("*").eq(match_column, match_value).execute()
    return resp.data or []

async def get_linked_minecraft_name_async(discord_id: int) -> str | None:
    acc = await arun(db.get_linked_account, discord_id)
    return acc.get("minecraft_name") if acc else None

async def get_tgf_cooldown(discord_id: int) -> int | None:
    # Ha van TGF cooldown táblád a Supabase-ben, innen kérhető le
    res = await arun(supabase_select, "tgf_cooldowns", "discord_id", discord_id)
    return res[0].get("cooldown_until") if res else None
