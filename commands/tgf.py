import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import datetime

from database import get_tgf_cooldown, set_tgf_cooldown
from commands.staff import is_staff_member, is_regulator_member

# ==========================================
# BEÁLLÍTÁSOK
# ==========================================
TGF_LOG_CHANNEL_ID = 1505522005028503582 
TGF_COOLDOWN_DAYS = 30 # 1 hónap

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
    "Szerinted a regulátor dolga inkább a moderálás vagy az ELO ellenőrzése?",
    "Elfogadod, ha egy magasabb rangú staff felülbírál?",
    "Mit teszel, ha látod, hogy egy játékosnak rossz ELO van megadva?",
    "Hogyan kezelsz egy játékost, aki nem fogadja el a tier döntésedet?",
    "Miért fontos szerinted, hogy részletesen tudd a szabályzatot?",
    "Miért téged válasszunk?",
    "Van valami egyéb dolog, amit szeretnéd, ha tudnánk rólad?"
]

# Globális szótár a megszakítások figyelésére
active_tgf_sessions = {}

# ==========================================
# STAFF BÍRÁLÓ NÉZET ÉS MODAL
# ==========================================
class TGFReviewModal(discord.ui.Modal):
    def __init__(self, applicant_id: int, action: str):
        title_str = "Jelentkezés elfogadása" if action == "accept" else "Jelentkezés elutasítása"
        super().__init__(title=title_str)
        self.applicant_id = applicant_id
        self.action = action

        self.reason = discord.ui.TextInput(
            label="Megjegyzés / Indoklás",
            style=discord.TextStyle.paragraph,
            placeholder="Ide írd a döntésed indokát a jelentkezőnek...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Cooldown beállítása a Supabase-ben (1 hónap)
        await set_tgf_cooldown(self.applicant_id, TGF_COOLDOWN_DAYS)

        guild = interaction.guild
        applicant = guild.get_member(self.applicant_id)
        
        # Embed frissítése a bíráló csatornában
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green() if self.action == "accept" else discord.Color.red()
        status_text = "✅ ELFOGADVA" if self.action == "accept" else "❌ ELUTASÍTVA"
        embed.title = f"{embed.title} - {status_text}"
        embed.add_field(name="Bíráló", value=interaction.user.mention, inline=False)
        embed.add_field(name="Megjegyzés", value=self.reason.value, inline=False)
        
        await interaction.message.edit(embed=embed, view=None)

        # DM küldése a jelentkezőnek
        if applicant:
            try:
                dm_embed = discord.Embed(
                    title="neotiers.hu | regulátor jelentkezés elbírálva",
                    description=f"A jelentkezésedet {interaction.user.mention} bírálta el.\n\n**Döntés:** {status_text}",
                    color=discord.Color.green() if self.action == "accept" else discord.Color.red()
                )
                dm_embed.add_field(name="A bíráló üzenete:", value=f"*{self.reason.value}*", inline=False)
                
                if self.action == "accept":
                    dm_embed.add_field(name="Következő lépés:", value="Kérjük, várj a további instrukciókra ebben a csatornában vagy a szerveren!", inline=False)
                
                dm_embed.set_footer(text="Fontos: Mindent látunk és minden logolva van. Mindig a szabályok alapján járj el. Mindenről készül biztonsági mentés!")
                await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        await interaction.followup.send("Döntés rögzítve, logolva és DM elküldve a játékosnak.", ephemeral=True)

class TGFReviewView(discord.ui.View):
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id

    @discord.ui.button(label="Elfogadás", style=discord.ButtonStyle.success, custom_id="tgf_accept")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("Nincs jogosultságod elbírálni!", ephemeral=True)
            return
        await interaction.response.send_modal(TGFReviewModal(self.applicant_id, "accept"))

    @discord.ui.button(label="Elutasítás", style=discord.ButtonStyle.danger, custom_id="tgf_reject")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("Nincs jogosultságod elbírálni!", ephemeral=True)
            return
        await interaction.response.send_modal(TGFReviewModal(self.applicant_id, "reject"))

# ==========================================
# JELENTKEZÉS VÉGE (BEKÜLDÉS / MÉGSEM)
# ==========================================
class TGFConfirmSubmitView(discord.ui.View):
    def __init__(self, answers: list, time_taken: str):
        super().__init__(timeout=300)
        self.answers = answers
        self.time_taken = time_taken
        self.submitted = False

    @discord.ui.button(label="Jelentkezés beküldése", style=discord.ButtonStyle.success)
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.submitted = True
        await interaction.response.defer()
        
        # Log csatorna megkeresése
        log_channel = interaction.client.get_channel(TGF_LOG_CHANNEL_ID)
        if not log_channel:
            await interaction.followup.send("Hiba: A bíráló csatorna nem található. Szólj egy adminnak!", ephemeral=True)
            return

        # Óriás Embed építése a válaszokból
        embed = discord.Embed(
            title="Új Regulátor Jelentkezés",
            description=f"**Jelentkező:** {interaction.user.mention} (`{interaction.user.name}`)\n**Kitöltési idő:** {self.time_taken}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        for idx, (q, a) in enumerate(self.answers):
            embed.add_field(name=f"{idx+1}. {q}", value=f"*{a}*"[:1024], inline=False)
        
        view = TGFReviewView(interaction.user.id)
        await log_channel.send(embed=embed, view=view)
        
        await interaction.followup.send("✅ **Sikeresen beküldve!** A vezetőség hamarosan elbírálja a jelentkezésedet.")
        self.stop()

    @discord.ui.button(label="Jelentkezés lezárása (Mégsem)", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.submitted = True
        await interaction.response.send_message("❌ Jelentkezés elvetve. Nem került beküldésre.")
        self.stop()

# ==========================================
# KÉRDÉSKÖZBENI LEZÁRÓ GOMB
# ==========================================
class TGFQuestionCancelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Jelentkezés lezárása", style=discord.ButtonStyle.danger)
    async def cancel_q_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.user_id:
            active_tgf_sessions[self.user_id] = "cancelled"
            await interaction.response.send_message("❌ Jelentkezés megszakítva.", ephemeral=True)

# ==========================================
# KÉRDÉSSOR (DM LOOP)
# ==========================================
async def start_tgf_interview(interaction: discord.Interaction):
    user = interaction.user
    
    # 60 perces (3600 másodperc) időkorlát
    MAX_TIME = 3600 
    start_time = time.time()
    end_time = start_time + MAX_TIME
    
    active_tgf_sessions[user.id] = "active"
    answers = []

    await interaction.response.send_message(
        f"✅ **Jelentkezés elindítva!** Határidő: <t:{int(end_time)}:R>", 
        ephemeral=True
    )

    for i, question in enumerate(QUESTIONS):
        if active_tgf_sessions.get(user.id) == "cancelled":
            return 

        time_left = end_time - time.time()
        if time_left <= 0:
            await user.send("⏳ **Lejárt az idő!** A jelentkezésed nem került beküldésre.")
            active_tgf_sessions.pop(user.id, None)
            return

        embed = discord.Embed(
            title="neotiers.hu | Regulátor - Kérdés",
            description=f"**{question}**",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Válaszként küldj egy üzenetet ide a botnak | Lejárat: {int(time_left/60)} perc | {i+1}/{len(QUESTIONS)} kérdés")

        view = TGFQuestionCancelView(user.id)
        msg = await user.send(embed=embed, view=view)

        def check(m):
            return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

        try:
            while True:
                response = await interaction.client.wait_for('message', check=check, timeout=time_left)
                
                if active_tgf_sessions.get(user.id) == "cancelled":
                    return 
                
                if response.content:
                    answers.append((question, response.content))
                    break 

        except asyncio.TimeoutError:
            await user.send("⏳ **Lejárt a 60 perces időkeret!** A jelentkezésed megszakadt.")
            active_tgf_sessions.pop(user.id, None)
            return

    # VÉGEZTÜNK AZ ÖSSZES KÉRDÉSSEL
    active_tgf_sessions.pop(user.id, None)
    total_time_seconds = int(time.time() - start_time)
    minutes, seconds = divmod(total_time_seconds, 60)
    time_str = f"{minutes} perc {seconds} másodperc"

    end_embed = discord.Embed(
        title="neotiers.hu | Regulátor jelentkezés",
        description=(
            f"✅ **Sikeresen megválaszoltad az összes kérdést!**\n\n"
            f"**Kitöltési idő:** {time_str}\n"
            f"**Felhasználó:** {user.mention}\n\n"
            f"Ha biztos vagy benne, hogy beküldöd a jelentkezést a Vezetőségnek, nyomd meg a **Jelentkezés beküldése** gombot!"
        ),
        color=discord.Color.green()
    )
    
    confirm_view = TGFConfirmSubmitView(answers, time_str)
    await user.send(embed=end_embed, view=confirm_view)

# ==========================================
# KEZDŐ DM GOMBOK (INDÍTÁS / MÉGSEM)
# ==========================================
class TGFStartDMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Jelentkezés elindítása", style=discord.ButtonStyle.success)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None)
        await start_tgf_interview(interaction)

    @discord.ui.button(label="Mégsem", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Jelentkezés elvetve.", ephemeral=True)
        await interaction.message.edit(view=None)
        self.stop()

# ==========================================
# SZERVERES FŐPANEL NÉZET
# ==========================================
class TGFPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ITT ÁTÍRVA: Secondary (szürke) gomb
    @discord.ui.button(label="Regulátor", style=discord.ButtonStyle.secondary, custom_id="tgf_panel_regulator")
    async def regulator_tgf_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cooldown_end = await get_tgf_cooldown(interaction.user.id)
        if cooldown_end:
            timestamp = int(cooldown_end.timestamp())
            await interaction.response.send_message(f"⏳ Jelenleg nem jelentkezhetsz! Újra próbálkozhatsz: <t:{timestamp}:R>", ephemeral=True)
            return

        try:
            embed = discord.Embed(
                title="neotiers.hu | Regulátor Jelentkezés",
                description=(
                    "Ha szeretnéd elkezdeni a jelentkezést, nyomd meg az **Indítás** gombot.\n\n"
                    "⏱️ A kitöltésre **60 perced** lesz.\n"
                    "💬 A kérdésekre itt, **DM-ben, egyesével** kell válaszolnod.\n"
                    "⚠️ Ha megszakítod vagy lejár az idő, a jelentkezés nem kerül beküldésre!"
                ),
                color=discord.Color.blue()
            )
            await interaction.user.send(embed=embed, view=TGFStartDMView())
            await interaction.response.send_message("✅ Elküldtük neked a jelentkezéshez szükséges adatokat Privát Üzenetben!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Nem tudok neked privát üzenetet küldeni! Kérlek engedélyezd a szervertagoktól a DM fogadását a beállításaidban.", ephemeral=True)

# ==========================================
# BOT PARANCS
# ==========================================
class TGFCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tgfpanel", description="Lerakja a TGF jelentkezési panelt (Admin parancs)")
    async def tgfpanel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Ehhez a parancshoz adminisztrátori jog szükséges!", ephemeral=True)
            return

        # ITT ÁTÍRVA: A cím "NeonTiers.hu | TGF Jelentkezés" lett, és a szín lila
        embed = discord.Embed(
            title="NeonTiers.hu | TGF Jelentkezés",
            description="Válaszd ki, melyik pozícióra szeretnél jelentkezni az alábbi gombra kattintva!",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="**Fontos tudnivalók:**", 
            value=(
                "**1.** Egy adott pozícióra 30 naponta (1 havonta) egyszer tudsz jelentkezni.\n"
                "**2.** A jelentkezést privát üzenetben (DM) kell kitöltened.\n"
                "**3.** A kitöltésre legfeljebb 60 perced van.\n"
                "**4.** A kérdéseket sorban kapod meg, visszalépni vagy átugrani nem lehet.\n"
                "**5.** A válaszokat a Staff részére megy és az bírálja el."
            ), 
            inline=False
        )

        await interaction.channel.send(embed=embed, view=TGFPanelView())
        await interaction.response.send_message("✅ Sikeresen lerakva!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TGFCog(bot))