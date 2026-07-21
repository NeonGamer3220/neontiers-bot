import discord
from discord.ext import commands, tasks
import json
import os
import re
import time

from config import BANNED_ROLE_ID

# Ugyanaz a csatorna, ahova a weboldal Ban Kezelője írja ki a kitiltásokat.
BAN_CHANNEL_ID = 1469803060976160822
BAN_DATA_FILE = "banned_players.json"

# A weboldalon választható időtartam-címkék -> napok száma.
# (Ugyanazok a szövegek, mint amiket a Ban Kezelő oldal generál a "Lejárat:" sorba.)
DURATION_DAYS = {
    "1 nap": 1,
    "3 nap": 3,
    "1 hét": 7,
    "2 hét": 14,
    "1 hónap": 30,
    "3 hónap": 90,
    "6 hónap": 180,
    "1 év": 365,
}

MENTION_RE = re.compile(r"<@!?(\d+)>")
LEJARAT_RE = re.compile(r"\*\*Lejárat:\*\*\s*(.+)")


def _load() -> dict:
    if not os.path.exists(BAN_DATA_FILE):
        return {}
    try:
        with open(BAN_DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    with open(BAN_DATA_FILE, "w") as f:
        json.dump(data, f)


def is_banned_by_role(member: discord.Member) -> bool:
    """Igaz, ha a tagnak van kitiltás role-ja (queue-ból/tesztelésből/tierekből ki van zárva)."""
    if member is None:
        return False
    return any(r.id == BANNED_ROLE_ID for r in getattr(member, "roles", []))


class BanEnforcementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_bans.start()

    def cog_unload(self):
        self.check_expired_bans.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Csak a bot saját üzeneteit figyeljük a ban-log csatornán
        if not self.bot.user or message.author.id != self.bot.user.id:
            return
        if not message.channel or message.channel.id != BAN_CHANNEL_ID:
            return
        if not message.guild:
            return

        content = message.content or ""
        mention_match = MENTION_RE.search(content)
        if not mention_match:
            return
        user_id = int(mention_match.group(1))

        lejarat_match = LEJARAT_RE.search(content)
        lejarat_text = lejarat_match.group(1).strip() if lejarat_match else ""

        expires_at = None  # None = végleges
        for label, days in DURATION_DAYS.items():
            if lejarat_text.startswith(label):
                expires_at = time.time() + days * 86400
                break

        role = message.guild.get_role(BANNED_ROLE_ID)
        if not role:
            print(f"[BAN ENFORCEMENT] ❌ Nem található a kitiltás role ({BANNED_ROLE_ID}) a szerveren.")
            return

        member = message.guild.get_member(user_id)
        if not member:
            try:
                member = await message.guild.fetch_member(user_id)
            except Exception:
                member = None

        if member:
            try:
                await member.add_roles(role, reason="NeonTiers ban (weboldal Ban Kezelő)")
            except Exception as e:
                print(f"[BAN ENFORCEMENT] ❌ Nem sikerült rátenni a kitiltás role-t: {e}")
        else:
            print(f"[BAN ENFORCEMENT] ⚠️ A kitiltott tag ({user_id}) nincs a szerveren, csak a nyilvántartásba kerül be.")

        data = _load()
        data[str(user_id)] = {"expires_at": expires_at, "guild_id": message.guild.id}
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
                continue  # végleges kitiltás, nem jár le automatikusan

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
                            print(f"[BAN ENFORCEMENT] ❌ Nem sikerült levenni a kitiltás role-t: {e}")

                del data[user_id_str]
                changed = True

        if changed:
            _save(data)

    @check_expired_bans.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(BanEnforcementCog(bot))
