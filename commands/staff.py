import discord
from discord.ext import commands
from discord import app_commands
import datetime
import time
import os
from typing import Optional

# Importáljuk a config és adatbázis adatokat
from config import (
    MODE_LIST, RANKS, POINTS, TICKET_TYPES, GAMEMODE_DISPLAY_NAMES,
    WEBSITE_URL, STAFF_ROLE_ID, REGULATOR_ROLE_ID,
    TESTER_ROLE_ID, EXTRA_STAFF_ROLE_IDS, ALLOWED_USER_IDS,
    DEBUG_ALLOWED_USERS, DEBUG_ALLOWED_ROLES
)
from config import (
    normalize_gamemode, get_gamemode_display_name, 
    get_gamemode_indicator, get_rank_value_min
)
from database import (
    get_linked_minecraft_name, api_get_elos,
    api_post_elo, api_rename_player, api_set_ban, api_remove_player,
    is_player_banned, ban_player, unban_player, supabase_select
)

def truncate_message(text: str, max_length: int = 1900) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

# ==========================================
# STAFF JOGOSULTSÁG ELLENŐRZŐK
# ==========================================
def is_staff_member(member: discord.Member) -> bool:
    if DEBUG_ALLOWED_USERS and member.id in DEBUG_ALLOWED_USERS:
        return True
    if DEBUG_ALLOWED_ROLES:
        for role_id in DEBUG_ALLOWED_ROLES:
            if any(r.id == role_id for r in member.roles):
                return True
    if ALLOWED_USER_IDS and member.id in ALLOWED_USER_IDS:
        return True
    if member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID and any(r.id == STAFF_ROLE_ID for r in member.roles):
        return True
    for role_id in EXTRA_STAFF_ROLE_IDS:
        if role_id and any(r.id == role_id for r in member.roles):
            return True
    return False

def is_regulator_member(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.id == REGULATOR_ROLE_ID for r in member.roles)

def can_assign_tier(member: discord.Member) -> bool:
    return is_staff_member(member) or any(r.id == TESTER_ROLE_ID for r in member.roles)

def can_assign_all_tiers(member: discord.Member) -> bool:
    return is_staff_member(member)

def _choices_from_list(values):
    return [app_commands.Choice(name=v, value=v) for v in values]

# ==========================================
# TIER SELECT AUTOMATIKUS MENÜS RENDSZER
# ==========================================
class GameModeSelect(discord.ui.Select):
    def __init__(self, mode_label: str, mode_key: str):
        options = [discord.SelectOption(label=label, value=key) for label, key, _rid in TICKET_TYPES]
        super().__init__(placeholder="Játékmód...", options=options, custom_id="gamemode_select")
        self.mode_label = mode_label
        self._default_value = mode_key

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class TierSelect(discord.ui.Select):
    def __init__(self, tester: discord.Member):
        if can_assign_all_tiers(tester):
            allowed_ranks = [rank for rank in RANKS if rank != "Unranked"]
        else:
            allowed_ranks = [rank for rank in RANKS if rank != "Unranked" and get_rank_value_min(rank) <= 6]
        
        options = [discord.SelectOption(label=rank, value=rank) for rank in allowed_ranks]
        super().__init__(placeholder="Elért ELO (rang)...", options=options, custom_id="tier_select")

    async def callback(self, interaction: discord.Interaction):
        selected_tier = self.values[0]
        view = self.view
        owner_id = view.owner_id
        linked_minecraft = view.linked_minecraft
        tester = view.tester
        mode_key = view.mode_key

        owner_member = interaction.guild.get_member(owner_id)
        if not owner_member:
            await interaction.response.send_message("Hiba: nem találom a Discord felhasználót.", ephemeral=True)
            return

        if WEBSITE_URL:
            try:
                mode_to_save = get_gamemode_display_name(mode_key)
                save = await api_post_elo(username=linked_minecraft, mode=mode_to_save, elo=selected_tier, tester=tester)
                save_ok = (save.get("status") == 200 or save.get("status") == 201)
                if save_ok:
                    await interaction.response.send_message(f"✅ ELO beállítva: **{selected_tier}** és mentve a weboldalra!", ephemeral=True)
                else:
                    await interaction.response.send_message(f"✅ ELO beállítva: **{selected_tier}** (weboldal mentés sikertelen)", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"✅ ELO beállítva: **{selected_tier}** (weboldal hiba: {e})", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ ELO beállítva: **{selected_tier}**", ephemeral=True)

class TierSelectView(discord.ui.View):
    def __init__(self, owner_id: int, linked_minecraft: str, mode_key: str, tester: discord.Member):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.linked_minecraft = linked_minecraft
        self.mode_key = mode_key
        self.tester = tester
        
        mode_label = mode_key
        for label, key, _rid in TICKET_TYPES:
            if key == mode_key:
                mode_label = label
                break
        self.mode_label = mode_label
        self.add_item(GameModeSelect(mode_label, mode_key))
        self.add_item(TierSelect(tester))

# ==========================================
# MEGERŐSÍTŐ NÉZET TÖRLÉSHEZ
# ==========================================
class ConfirmRemoveView(discord.ui.View):
    def __init__(self, username: str, actual_username: str, moderator: discord.Member):
        super().__init__(timeout=60)
        self.username = username
        self.actual_username = actual_username
        self.moderator = moderator
        self.confirmed = False

    @discord.ui.button(label="Igen, törlöm", style=discord.ButtonStyle.danger, custom_id="confirm_remove_yes")
    async def confirm_yes(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója erősítheti meg.", ephemeral=True)
            return

        self.confirmed = True
        await interaction.response.defer()

        try:
            result = await api_remove_player(username=self.actual_username)
            status = result.get("status")
            data = result.get("data", {})

            if status == 200:
                modes = data.get("modes", "Összes")
                desc = f"**{self.username}** sikeresen törölve lett a tierlistáról.\nMód: {modes}"
                embed = discord.Embed(title="✅ Játékos eltávolítva a tierlistáról", description=desc, color=discord.Color.green())
                embed.set_footer(text=f"Moderátor: {self.moderator.display_name}")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(f"❌ Hiba a törléskor.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {e}", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Mégse", style=discord.ButtonStyle.secondary, custom_id="confirm_remove_no")
    async def confirm_no(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.moderator.id:
            await interaction.response.send_message("❌ Csak a parancs indítója mondhat le.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Törlés megszüntetve.", ephemeral=True)
        self.stop()

# ==========================================
# STAFF COG OSZTÁLY
# ==========================================
class StaffCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="testresult", description="Tesztelési eredmény feljegyzése (staff csak)")
    @app_commands.describe(username="Minecraft név", tester="Tesztelő (Discord user)", gamemode="Játékmód", rank="Elért rang (ELO)")
    @app_commands.choices(gamemode=_choices_from_list(MODE_LIST), rank=_choices_from_list(RANKS))
    async def testresult(self, interaction: discord.Interaction, username: str, tester: discord.Member, gamemode: app_commands.Choice[str], rank: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)

        try:
            if not is_staff_member(interaction.user):
                await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
                return

            mode_val = gamemode.value
            rank_val = rank.value
            prev_rank = "500" # Mivel ELO-s a rendszer, az alapérték 500

            if WEBSITE_URL:
                try:
                    res = await api_get_elos(username=username, mode=mode_val)
                    if res.get("status") == 200:
                        data = res.get("data", {})
                        target = data.get("elo") or (data.get("elos", [None])[0])
                        if target:
                            prev_rank = str(target.get("elo", "500")) or "500"
                except: pass

            skin_url = f"https://minotar.net/helm/{username}/128.png"
            mode_key_for_indicator = normalize_gamemode(mode_val)
            indicator = get_gamemode_indicator(mode_key_for_indicator)

            embed = discord.Embed(
                title="Eredmény bejegyzés",
                description=f"{tester.mention} **{rank_val} ELO-t** állított be {username} játékosnak {indicator} **{mode_val}** játékmódból.",
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=skin_url)
            embed.set_footer(text=f"Időpont: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            if not WEBSITE_URL:
                await interaction.followup.send("⚠️ WEBSITE_URL nincs beállítva, nem mentem webre.", ephemeral=True)
                return

            mode_to_save = get_gamemode_display_name(mode_val)
            save = await api_post_elo(username=username, mode=mode_to_save, elo=rank_val, tester=tester)
            save_ok = save.get("save_ok", save.get("status") in (200, 201, 204))

            tier_channel_id = int(os.getenv("TIER_RESULTS_CHANNEL_ID", "0"))
            if tier_channel_id:
                tier_channel = interaction.guild.get_channel(tier_channel_id)
                if tier_channel:
                    await tier_channel.send(embed=embed)
                    await interaction.followup.send(f"✅ Eredmény mentve! Előző ELO: **{prev_rank}** → Új ELO: **{rank_val}**", ephemeral=True)
                    return

            if save_ok:
                await interaction.followup.send(f"✅ Mentve + weboldal frissítve.\nElőző ELO: **{prev_rank}** → Új ELO: **{rank_val}**", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Mentés hiba a weboldal felé.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(name="tierlistnamechange", description="Játékos nevének megváltoztatása a tierlistán (admin csak)")
    async def tierlistnamechange(self, interaction: discord.Interaction, oldname: str, newname: str):
        await interaction.response.defer(ephemeral=True)
        if not is_regulator_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        result = await api_rename_player(old_name=oldname, new_name=newname)
        if result.get("status") == 200:
            await interaction.followup.send(f"✅ Sikeresen átnevezve: **{oldname}** → **{newname}**", ephemeral=True)
        else:
            await interaction.followup.send("❌ Hiba történt az átnevezés során.", ephemeral=True)

    @app_commands.command(name="tierlistban", description="Játékos kitiltása a tesztelésből (admin csak).")
    async def tierlistban(self, interaction: discord.Interaction, name: str, days: int, reason: str = ""):
        await interaction.response.defer(ephemeral=True)
        if not is_regulator_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if is_player_banned(name):
            await interaction.followup.send(f"❌ **{name}** már kitiltás alatt áll.", ephemeral=True)
            return

        ban_player(name, days, reason)
        expires_at = 0 if days == 0 else int(time.time() + (days * 24 * 60 * 60))
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=True, expires_at=expires_at, reason=reason)

        await interaction.followup.send(f"✅ **{name}** sikeresen ki lett tiltva {days} napra.", ephemeral=True)

    @app_commands.command(name="tierlistunban", description="Játékos visszavétele a tesztelésbe (admin csak).")
    async def tierlistunban(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        if not is_regulator_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        if not is_player_banned(name):
            await interaction.followup.send(f"❌ **{name}** nincs kitiltva.", ephemeral=True)
            return

        unban_player(name)
        if WEBSITE_URL:
            await api_set_ban(username=name, banned=False)
        await interaction.followup.send(f"✅ **{name}** sikeresen vissza lett engedve.", ephemeral=True)

    @app_commands.command(name="removetierlist", description="Játékos eltávolítása a tierlistáról (admin csak, DANGER!)")
    async def removetierlist(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        if not is_regulator_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez a parancshoz.", ephemeral=True)
            return

        view = ConfirmRemoveView(username=name, actual_username=name, moderator=interaction.user)
        embed = discord.Embed(title="⚠️ FIGYELMEZTETÉS - Törlés előtt!", description=f"Biztosan véglegesen törlöd **{name}** minden eredményét?", color=discord.Color.red())
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="report", description="Heti riport: hány embert teszteltek az elmúlt 7 napban (Admin only)")
    @app_commands.describe(channel="Melyik csatornába küldjem a riportot? (alapértelmezett: ez a csatorna)")
    async def report(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        target_channel = channel or interaction.channel

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

        try:
            all_tests = await supabase_select("tests")
        except Exception as e:
            return await interaction.followup.send(f"❌ Hiba az adatok lekérésekor: {e}", ephemeral=True)

        tested_usernames = set()
        total_tests = 0
        per_mode = {}

        for t in all_tests:
            created_at_raw = t.get("created_at")
            if not created_at_raw:
                continue
            try:
                created_dt = datetime.datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=datetime.timezone.utc)
            except Exception:
                continue

            if created_dt >= since:
                total_tests += 1
                uname = t.get("username")
                if uname:
                    tested_usernames.add(str(uname).lower())
                mode = t.get("gamemode", "Ismeretlen")
                per_mode[mode] = per_mode.get(mode, 0) + 1

        embed = discord.Embed(
            title="📊 Heti Tesztelési Riport",
            description="Az elmúlt **7 nap** tesztelési statisztikái.",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Tesztelt egyedi játékosok", value=str(len(tested_usernames)), inline=True)
        embed.add_field(name="Összes rögzített teszt", value=str(total_tests), inline=True)

        if per_mode:
            mode_lines = "\n".join(f"**{m}**: {c}" for m, c in sorted(per_mode.items(), key=lambda x: -x[1]))
            embed.add_field(name="Játékmódok szerinti bontás", value=mode_lines[:1024], inline=False)
        else:
            embed.add_field(name="Játékmódok szerinti bontás", value="Nincs adat az elmúlt 7 napból.", inline=False)

        embed.set_footer(text=f"Generálta: {interaction.user.display_name}")

        try:
            await target_channel.send(embed=embed)
            await interaction.followup.send(f"✅ Riport elküldve ide: {target_channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba a riport küldésekor: {e}", ephemeral=True)

    @app_commands.command(name="bulkimport", description="Bulk import test results from file (admin only)")
    async def bulkimport(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if not is_regulator_member(interaction.user):
            await interaction.followup.send("Nincs jogosultságod ehhez.", ephemeral=True)
            return

        try:
            content = await file.read()
            data = content.decode('utf-8')
            lines = data.strip().split('\n')
            success_count = 0

            for line in lines:
                parts = line.strip().split()
                if len(parts) < 3: continue
                username, mode, rank = parts[0], parts[1].lower(), parts[2].upper()
                mode_display = get_gamemode_display_name(mode)
                save = await api_post_elo(username=username, mode=mode_display, elo=rank, tester=interaction.user)
                if save.get("status") in [200, 201]: success_count += 1

            await interaction.followup.send(f"✅ Sikeresen importálva: {success_count} db bejegyzés.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba az importálás során: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(StaffCog(bot))