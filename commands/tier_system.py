import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import datetime

from config import TIER_RESULTS_CHANNEL_ID, get_gamemode_display_name
from database import api_post_elo_instant

COOLDOWN_FILE = "tier_cooldowns.json"

def _load_cooldowns() -> dict:
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cooldowns(data: dict):
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[COOLDOWN SAVE ERROR] {e}")

class SubmitTierModal(discord.ui.Modal, title="Eredmény Rögzítése"):
    player_mc = discord.ui.TextInput(label="Játékos Minecraft neve", placeholder="Minecraft_Név", required=True)
    gamemode = discord.ui.TextInput(label="Játékmód", placeholder="Sword, Mace, stb.", required=True)
    achieved_tier = discord.ui.TextInput(label="Elért Tier / Rang", placeholder="HT3, LT2, Unranked", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        mc_name = self.player_mc.value.strip()
        mode_display = get_gamemode_display_name(self.gamemode.value.strip())
        rank_val = self.achieved_tier.value.strip().upper()

        # Instant Upsert Hívás az azonnali rögzítéshez
        success = await api_post_elo_instant(
            username=mc_name,
            mode=mode_display,
            elo=rank_val,
            tester=interaction.user.display_name
        )

        if success:
            res_channel = interaction.guild.get_channel(TIER_RESULTS_CHANNEL_ID)
            if res_channel:
                embed = discord.Embed(
                    title="📊 Új Tier Eredmény Rögzítve!",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Játékos", value=f"`{mc_name}`", inline=True)
                embed.add_field(name="Játékmód", value=mode_display, inline=True)
                embed.add_field(name="Elért Tier", value=f"**{rank_val}**", inline=True)
                embed.set_footer(text=f"Tesztelő: {interaction.user.display_name}")
                await res_channel.send(embed=embed)

            await interaction.followup.send(f"⚡ **Azonnal rögzítve!** `{mc_name}` -> `{mode_display}`: **{rank_val}**", ephemeral=True)
        else:
            await interaction.followup.send("❌ Hiba történt az eredmény mentésekor az adatbázisba.", ephemeral=True)

class QueueControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Eredmény Rögzítése", style=discord.ButtonStyle.success, custom_id="queue_submit_result")
    async def submit_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Csak Regulátorok/Staffok használhatják!", ephemeral=True)
        await interaction.response.send_modal(SubmitTierModal())

class TierSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="clearcooldown", description="Törli egy játékos cooldownját egy adott játékmódban.")
    async def clearcooldown(self, interaction: discord.Interaction, tag: discord.Member, gamemode: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Csak Adminoknak!", ephemeral=True)

        data = _load_cooldowns()
        p_id = str(tag.id)
        mode_key = gamemode.lower().strip()

        if p_id in data and mode_key in data[p_id]:
            del data[p_id][mode_key]
            if not data[p_id]:
                del data[p_id]
            _save_cooldowns(data)
            await interaction.response.send_message(f"✅ Sikeresen törölted {tag.mention} cooldownját a(z) `{mode_key}` játékmódban!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {tag.mention} játékosnak nincs aktív cooldownja ebben a játékmódban.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TierSystemCog(bot))
