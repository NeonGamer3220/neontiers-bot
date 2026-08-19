"""
NeonTiers Bot - Ötlet Csatorna (commands/idea_channel.py)

/otletcsatorna-beallitas <csatorna>  -> beállítja az ötletek csatornáját
/otletcsatorna-torles                -> törli a beállítást
/otletcsatorna-info                  -> megmutatja az aktuális beállítást

Ha valaki üzenetet küld a beállított csatornába, a bot törli az eredeti
üzenetet, és helyette egy "Új ötlet!" embedet küld ✅ / ❌ szavazógombokkal.
A gombok perzisztensek, újraindítás után is működnek.
"""

import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("neontiers.commands.idea_channel")

CONFIG_FILE = "idea_channel_config.json"
VOTES_FILE = "idea_votes.json"


# ==========================================
# JSON SEGÉDFÜGGVÉNYEK
# ==========================================
def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.error("Hiba a(z) %s mentésekor: %s", path, exc)


def get_idea_channel_id(guild_id: int) -> int | None:
    config = _load_json(CONFIG_FILE)
    value = config.get(str(guild_id))
    return int(value) if value else None


def set_idea_channel_id(guild_id: int, channel_id: int) -> None:
    config = _load_json(CONFIG_FILE)
    config[str(guild_id)] = channel_id
    _save_json(CONFIG_FILE, config)


def remove_idea_channel_id(guild_id: int) -> None:
    config = _load_json(CONFIG_FILE)
    if str(guild_id) in config:
        del config[str(guild_id)]
        _save_json(CONFIG_FILE, config)


# ==========================================
# EMBED ÉPÍTÉS
# ==========================================
def build_idea_embed(author: discord.abc.User, content: str, approve: list, reject: list) -> discord.Embed:
    embed = discord.Embed(
        title="💡 Új ötlet!",
        description=(
            f"**Ötlet létrehozó:** {author.mention} | {author}\n\n"
            f"✅ **támogatom**       ❌ **elutasítom**\n\n"
            f"> {content}"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"👍 {len(approve)} támogatás  •  👎 {len(reject)} elutasítás")
    return embed


# ==========================================
# PERZISZTENS SZAVAZÓ VIEW
# ==========================================
class IdeaVoteView(discord.ui.View):
    """
    Statikus custom_id-jű, perzisztens View. A szavazatokat mindig a
    ténylegesen kattintott üzenet (interaction.message.id) alapján
    tároljuk/olvassuk, így ez az egy View példány minden ötlet-üzenethez
    használható, újraindítás után is.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _handle_vote(self, interaction: discord.Interaction, vote: str) -> None:
        message = interaction.message
        votes = _load_json(VOTES_FILE)
        entry = votes.get(str(message.id))

        if entry is None:
            # Ha valamiért nincs még rögzítve (pl. régi üzenet), létrehozzuk.
            author_id = None
            if message.embeds and message.embeds[0].description:
                pass
            entry = {"approve": [], "reject": [], "author_id": author_id, "content": ""}

        approve = set(entry.get("approve", []))
        reject = set(entry.get("reject", []))
        uid = interaction.user.id

        if vote == "approve":
            if uid in approve:
                approve.discard(uid)
            else:
                approve.add(uid)
                reject.discard(uid)
        else:
            if uid in reject:
                reject.discard(uid)
            else:
                reject.add(uid)
                approve.discard(uid)

        entry["approve"] = list(approve)
        entry["reject"] = list(reject)
        votes[str(message.id)] = entry
        _save_json(VOTES_FILE, votes)

        # Gombfeliratok frissítése
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "idea_vote_approve":
                    child.label = str(len(approve))
                elif child.custom_id == "idea_vote_reject":
                    child.label = str(len(reject))

        embed = message.embeds[0] if message.embeds else None
        if embed:
            embed.set_footer(text=f"👍 {len(approve)} támogatás  •  👎 {len(reject)} elutasítás")

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="0", emoji="✅", style=discord.ButtonStyle.success, custom_id="idea_vote_approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_vote(interaction, "approve")

    @discord.ui.button(label="0", emoji="❌", style=discord.ButtonStyle.danger, custom_id="idea_vote_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._handle_vote(interaction, "reject")


# ==========================================
# COG
# ==========================================
class IdeaChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    otletcsatorna = app_commands.Group(
        name="otletcsatorna",
        description="Az ötletek csatorna beállításai.",
        default_permissions=discord.Permissions(administrator=True)
    )

    @otletcsatorna.command(name="beallitas", description="Beállítja a csatornát, ahová az ötleteket lehet küldeni.")
    @app_commands.describe(csatorna="A csatorna, ahol az ötlet-embedek megjelennek.")
    @app_commands.checks.has_permissions(administrator=True)
    async def beallitas(self, interaction: discord.Interaction, csatorna: discord.TextChannel) -> None:
        set_idea_channel_id(interaction.guild.id, csatorna.id)
        await interaction.response.send_message(
            f"✅ Az ötletek csatornája beállítva: {csatorna.mention}\n"
            f"Mostantól minden ide küldött üzenetből automatikusan ötlet-embed készül szavazógombokkal.",
            ephemeral=True
        )

    @otletcsatorna.command(name="torles", description="Törli a beállított ötletek csatornáját.")
    @app_commands.checks.has_permissions(administrator=True)
    async def torles(self, interaction: discord.Interaction) -> None:
        remove_idea_channel_id(interaction.guild.id)
        await interaction.response.send_message("✅ Az ötletek csatorna beállítása törölve.", ephemeral=True)

    @otletcsatorna.command(name="info", description="Megmutatja az aktuálisan beállított ötletek csatornáját.")
    @app_commands.checks.has_permissions(administrator=True)
    async def info(self, interaction: discord.Interaction) -> None:
        channel_id = get_idea_channel_id(interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message("ℹ️ Jelenleg nincs beállítva ötletek csatorna.", ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        mention = channel.mention if channel else f"`{channel_id}` (nem található csatorna)"
        await interaction.response.send_message(f"ℹ️ Jelenlegi ötletek csatorna: {mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        channel_id = get_idea_channel_id(message.guild.id)
        if not channel_id or message.channel.id != channel_id:
            return

        content = message.content.strip()
        attachments = message.attachments

        if not content and not attachments:
            return

        # Ha üresen küldene valaki (pl. csak parancsot), hagyjuk figyelmen kívül
        if content.startswith("/"):
            return

        author = message.author
        can_delete = message.channel.permissions_for(message.guild.me).manage_messages

        try:
            embed = build_idea_embed(author, content or "*(csak melléklet)*", [], [])
            if attachments:
                embed.set_image(url=attachments[0].url)

            view = IdeaVoteView()
            sent = await message.channel.send(embed=embed, view=view)

            votes = _load_json(VOTES_FILE)
            votes[str(sent.id)] = {
                "approve": [],
                "reject": [],
                "author_id": author.id,
                "guild_id": message.guild.id,
                "content": content
            }
            _save_json(VOTES_FILE, votes)

            if can_delete:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
        except Exception as exc:
            log.error("Hiba az ötlet-embed létrehozásakor: %s", exc)

    @beallitas.error
    @torles.error
    @info.error
    async def idea_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Ehhez a parancshoz adminisztrátor jogosultság szükséges!", ephemeral=True)
        else:
            log.error("Hiba az otletcsatorna parancsban: %s", error)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Hiba történt: `{error}`", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IdeaChannelCog(bot))
