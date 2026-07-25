import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
from config import SUPABASE_URL, SUPABASE_KEY

class WeeklyReportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="report", description="Heti összesítő riport a teszterekről és regulatorokról.")
    @app_commands.checks.has_permissions(administrator=True) # Vagy módosítsd a jogosultságot igény szerint
    async def weekly_report(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not SUPABASE_URL or not SUPABASE_KEY:
            await interaction.followup.send("❌ A Supabase konfiguráció (URL vagy KEY) hiányzik a config.py-ból.")
            return

        # Elmúlt 7 nap kezdő időpontja (ISO formátumban, UTC)
        seven_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        base_supabase_url = SUPABASE_URL.rstrip('/')

        try:
            async with aiohttp.ClientSession() as session:
                
                # --- 1. TESZTEREK LEKÉRDEZÉSE (tests tábla, az új tester_id oszlop alapján) ---
                tests_url = f"{base_supabase_url}/rest/v1/tests?created_at=gte.{seven_days_ago}&select=tester_id"
                async with session.get(tests_url, headers=headers) as resp:
                    if resp.status == 200:
                        tests_data = await resp.json()
                    else:
                        tests_data = []

                # Teszterek számlálása tester_id alapján
                tester_counts = {}
                for row in tests_data:
                    t_id = row.get("tester_id")
                    if t_id:
                        tester_counts[t_id] = tester_counts.get(t_id, 0) + 1

                # --- 2. REGULATOROK LEKÉRDEZÉSE (discord_notifications tábla) ---
                notif_url = f"{base_supabase_url}/rest/v1/discord_notifications?created_at=gte.{seven_days_ago}&select=username,player_discord_id"
                async with session.get(notif_url, headers=headers) as resp:
                    if resp.status == 200:
                        notif_data = await resp.json()
                    else:
                        notif_data = []

                # Regulatorok számlálása
                regulator_counts = {}
                for row in notif_data:
                    reg_key = row.get("player_discord_id") or row.get("username")
                    if reg_key:
                        regulator_counts[reg_key] = regulator_counts.get(reg_key, 0) + 1

                # --- EMBED ÉPÍTÉSE ---
                embed = discord.Embed(
                    title="📊 Heti Teljesítmény Riport",
                    description="Az elmúlt **7 nap** összesített statisztikái a teszterekről és regulatorokról:",
                    color=discord.Color.blurple()
                )

                # Teszterek listájának formázása
                if tester_counts:
                    sorted_testers = sorted(tester_counts.items(), key=lambda x: x[1], reverse=True)
                    tester_lines = []
                    for t_id, count in sorted_testers:
                        if str(t_id).isdigit():
                            tester_lines.append(f"• <@{t_id}> – **{count}** teszt")
                        else:
                            tester_lines.append(f"• `{t_id}` – **{count}** teszt")
                    tester_text = "\n".join(tester_lines)
                else:
                    tester_text = "*Nem történt teszt az elmúlt 7 napban.*"

                embed.add_field(name="⚔️ Teszterek (Elvégzett tesztek)", value=tester_text, inline=False)

                # Regulatorok listájának formázása
                if regulator_counts:
                    sorted_regulators = sorted(regulator_counts.items(), key=lambda x: x[1], reverse=True)
                    reg_lines = []
                    for r_key, count in sorted_regulators:
                        if str(r_key).isdigit():
                            reg_lines.append(f"• <@{r_key}> – **{count}** magas eredmény")
                        else:
                            reg_lines.append(f"• `{r_key}` – **{count}** magas eredmény")
                        reg_text = "\n".join(reg_lines)
                else:
                    reg_text = "*Nem érkezett magas eredmény az elmúlt 7 napban.*"

                embed.add_field(name="🛡️ Regulatorok (Weboldalas rögzítések)", value=reg_text, inline=False)

                embed.set_footer(text=f"Időszak: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')} - Előző 7 nap")

                await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"[REPORT ERROR] {e}")
            await interaction.followup.send(f"❌ Hiba történt a riport generálása közben: {str(e)}")

async def setup(bot):
    await bot.add_cog(WeeklyReportCog(bot))
