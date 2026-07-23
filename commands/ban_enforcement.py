import discord
from discord.ext import commands, tasks
import json
import os
import re
import time

from config import BANNED_ROLE_ID, BAN_CHANNEL_ID

BAN_DATA_FILE = "banned_players.json"

DURATION_DAYS = {
    "1 nap": 1, "3 nap": 3, "1 hét": 7, "2 hét": 14,
    "1 hónap": 30, "3 hónap": 90, "6 hónap": 180, "1 év": 365,
}

MENTION_RE = re.compile(r"<@!?(\d+)>")
LEJARAT_RE = re.compile(r"\*\*Lejárat:\*\*\s*(.+)")

def _load() -> dict:
    if not os.path.exists(BAN_DATA_FILE):
        return {}
    try:
        with open(BAN_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[BAN ENFORCEMENT ERROR] Fájl olvasási hiba: {e}")
        return {}

def _save(data: dict):
    try:
        with open(BAN_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[BAN ENFORCEMENT ERROR] Fájl írási hiba: {e}")

def is_banned_by_role(member: discord.Member) -> bool:
    if not member or not hasattr(member, "roles"):
        return False
    return any(r.id == BANNED_ROLE_ID for r in member.roles)

class BanEnforcementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_bans.start()

    def cog_unload(self):
        self.check_expired_bans.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot and message.author.id == self.bot.user.id:
            return

        if message.channel.id != BAN_CHANNEL_ID:
            return

        m = MENTION_RE.search(message.content)
        if not m:
            return
        user_id = int(m.group(1))

        duration_days = None
        lej_match = LEJARAT_RE.search(message.content)
        if lej_match:
            raw_str = lej_match.group(1).strip()
            for key, days in DURATION_DAYS.items():
                if key.lower() in raw_str.lower():
                    duration_days = days
                    break

        expires_at = (time.time() + duration_days * 86400) if duration_days else None

        guild = message.guild
        if guild:
            role = guild.get_role(BANNED_ROLE_ID)
            member = guild.get_member(user_id)
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None

            if role and member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Weboldal / Ban csatorna bejegyzés")
                except Exception as e:
                    print(f"[BAN ENFORCEMENT] ❌ Nem sikerült rátenni a kitiltási rangot: {e}")

        data = _load()
        data[str(user_id)] = {
            "expires_at": expires_at,
            "guild_id": message.guild.id if message.guild else None
        }
        _save(data)

    @tasks.loop(minutes=30)
    async def check_expired_bans(self):
        data = _load()
        if not data:
            return

        now = time.time()
        changed = False

        for user_id_str, info in list(data.items()):
            expires_at = info.get("expires_at")
            if expires_at is None:
                continue

            if now >= expires_at:
                guild = self.bot.get_guild(info.get("guild_id"))
                if guild:
                    role = guild.get_role(BANNED_ROLE_ID)
                    member = guild.get_member(int(user_id_str))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(user_id_str))
                        except Exception:
                            member = None
                    if role and member:
                        try:
                            await member.remove_roles(role, reason="Kitiltás lejárt")
                        except Exception as e:
                            print(f"[BAN ENFORCEMENT] ❌ Hiba a role levételekor: {e}")

                del data[user_id_str]
                changed = True

        if changed:
            _save(data)

    @check_expired_bans.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(BanEnforcementCog(bot))
