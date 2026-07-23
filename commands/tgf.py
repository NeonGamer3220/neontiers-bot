import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime

from database import get_tgf_cooldown, set_tgf_cooldown
from commands.staff import is_staff_member
from config import TGF_LOG_CHANNEL_ID, TGF_COOLDOWN_DAYS

QUESTIONS = [
    "Mi a Minecraft felhasználóneved?",
    "Mi a Discord felhasználóneved?",
    "Hány éves vagy?",
    "Mióta vagy a neotiers közösség tagja?",
    "Mennyi időt tudsz aktívan a szerverre fordítani?",
    "Tisztában vagy-e a szabályokkal és be tudod-e tartani?",
    "Mit tennél, ha egy másik regulátor tévedne?",
    "Miért fontos a regulátor semlegessége?",
    "Mit gondolsz a gyűlöletbeszédről és a toxikus viselkedésről?",
    "Mit csinálsz, ha két játékos tesztelésen vitatkozik?",
    "Mit tennél, ha nem lennél biztos valamiben?",
    "Szerinted a regulátor feladata inkább az ELO-k ellenőrzése, vagy a játékosok segítése?",
    "Van-e valami hasonló staff tapasztalatod?",
    "Szerinted a regulátor dolga inkább a moderálás vagy az aktivitás fenntartása?"
]

class TGFActionModal(discord.ui.Modal):
    def __init__(self, action: str, applicant: discord.User):
        title = "Jelentkezés Elfogadása" if action == "accept" else "Jelentkezés Elutasítása"
        super().__init__(title=title)
        self.action = action
        self.applicant = applicant

        self.reason = discord.ui.TextInput(
            label="Indoklás / Megjegyzés",
            style=discord.TextStyle.paragraph,
            placeholder="Írd le a döntés indokát...",
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        status_text = "🟢 **ELFOGADVA**" if self.action == "accept" else "🔴 **ELUTASÍTVA**"
        color = discord.Color.green() if self.action == "accept" else discord.Color.red()

        original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
        
        if original_embed:
            new_embed = original_embed.copy()
            new_embed.color = color
            new_embed.add_field(name="Bírálat", value=f"{status_text}\n**Bíráló:** {interaction.user.mention}\n**Indok:** {self.reason.value}", inline=False)
            await interaction.message.edit(embed=new_embed, view=None)

        try:
            dm_embed = discord.Embed(
                title=f"TGF Jelentkezés Bírálat - {status_text}",
                description=f"A jelentkezésed elbírálásra került.\n\n**Bíráló:** {interaction.user.display_name}\n**Indok:** {self.reason.value}",
                color=color
            )
            await self.applicant.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.followup.send(f"✅ Jelentkezés sikeresen {self.action}-olva!", ephemeral=True)

class TGFDecisionView(discord.ui.View):
    def __init__(self, applicant: discord.User):
        super().__init__(timeout=None)
        self.applicant = applicant

    @discord.ui.button(label="Elfogadás", style=discord.ButtonStyle.success, custom_id="tgf_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Nincs jogosultságod ehhez!", ephemeral=True)
        await interaction.response.send_modal(TGFActionModal("accept", self.applicant))

    @discord.ui.button(label="Elutasítás", style=discord.ButtonStyle.danger, custom_id="tgf_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Nincs jogosultságod ehhez!", ephemeral=True)
        await interaction.response.send_modal(TGFActionModal("reject", self.applicant))

class TGFPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Jelentkezés Regulátornak", style=discord.ButtonStyle.primary, custom_id="tgf_apply_button")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        cooldown_dt = await get_tgf_cooldown(user.id)
        if cooldown_dt:
            timestamp = int(cooldown_dt.timestamp())
            return await interaction.response.send_message(
                f"❌ Legutóbb már jelentkeztél! Legközelebb ekkor jelentkezhetsz: <t:{timestamp}:R>",
                ephemeral=True
            )

        try:
            dm_channel = await user.create_dm()
            await dm_channel.send("👋 Szia! Elkezdődik a TGF jelentkezési folyamat. 60 perced van válaszolni a kérdésekre.")
            await interaction.response.send_message("📩 Elküldtem a kérdéseket privát üzenetben (DM)!", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Nem tudok neked privát üzenetet küldeni! Engedélyezd a DM-eket a szerver beállításaiban.", ephemeral=True)

        asyncio.create_task(self.run_interview(interaction, user, dm_channel))

    async def run_interview(self, interaction: discord.Interaction, user: discord.User, dm_channel: discord.DMChannel):
        answers = []
        
        def check(m):
            return m.author.id == user.id and m.channel.id == dm_channel.id

        for i, question in enumerate(QUESTIONS, 1):
            embed = discord.Embed(
                title=f"Kérdés {i}/{len(QUESTIONS)}",
                description=question,
                color=discord.Color.purple()
            )
            await dm_channel.send(embed=embed)

            try:
                msg = await interaction.client.wait_for("message", check=check, timeout=3600)
                answers.append((question, msg.content))
            except asyncio.TimeoutError:
                return await dm_channel.send("⏱️ Letelt a 60 perc! A jelentkezésed megszakadt.")

        log_channel = interaction.guild.get_channel(TGF_LOG_CHANNEL_ID) if interaction.guild else None
        if log_channel:
            log_embed = discord.Embed(
                title=f"📥 Új TGF Jelentkezés: {user.display_name}",
                description=f"**Jelentkező:** {user.mention} ({user.id})",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            for q, a in answers:
                log_embed.add_field(name=q, value=a[:1020] if a else "Üres", inline=False)

            await log_channel.send(embed=log_embed, view=TGFDecisionView(user))

        await set_tgf_cooldown(user.id, days=TGF_COOLDOWN_DAYS)
        await dm_channel.send("✅ Köszönjük! A jelentkezésedet elküldtük a Staff csapatnak elbírálásra.")

class TGFCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tgfpanel", description="Lerakja a TGF jelentkezési panelt (Admin)")
    async def tgfpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Ehhez a parancshoz adminisztrátori jog szükséges!", ephemeral=True)

        embed = discord.Embed(
            title="NeonTiers.hu | TGF Jelentkezés",
            description="Válaszd ki, melyik pozícióra szeretnél jelentkezni az alábbi gombra kattintva!",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="**Fontos tudnivalók:**",
            value=(
                "**1.** Egy adott pozícióra 30 naponta egyszer tudsz jelentkezni.\n"
                "**2.** A jelentkezést privát üzenetben (DM) kell kitöltened.\n"
                "**3.** A kitöltésre legfeljebb 60 perced van.\n"
                "**4.** A válaszokat a Staff bírálja el."
            ),
            inline=False
        )

        await interaction.channel.send(embed=embed, view=TGFPanelView())
        await interaction.response.send_message("✅ TGF Panel sikeresen kihelyezve!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TGFCommandCog(bot))
