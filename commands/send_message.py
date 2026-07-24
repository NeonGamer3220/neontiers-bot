"""
NeonTiers Bot - SendMessage Parancs (commands/send_message.py)
A hiányzó /sendmessage parancs megvalósítása.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("neontiers.commands.send_message")


class SendMessageCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="sendmessage", 
        description="Üzenet vagy Embed küldése egy megadott csatornába a bot nevében."
    )
    @app_commands.describe(
        csatorna="A célcsatorna, ahová az üzenetet küldeni szeretnéd.",
        uzenet="Az elküldendő szöveges üzenet.",
        cim="Opcionális: Az Embed címe (ha ki szeretnéd emelni az üzenetet).",
        kep_url="Opcionális: Kép URL beágyazása az üzenetbe."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sendmessage(
        self, 
        interaction: discord.Interaction, 
        csatorna: discord.TextChannel, 
        uzenet: str,
        cim: str | None = None,
        kep_url: str | None = None
    ) -> None:
        try:
            # Ha van megadva cím vagy kép, Embedként küldjük el
            if cim or kep_url:
                embed = discord.Embed(
                    title=cim if cim else "",
                    description=uzenet,
                    color=discord.Color.blue()
                )
                if kep_url:
                    embed.set_image(url=kep_url)
                
                embed.set_footer(text=f"NeonTiers.hu • Küldte: {interaction.user.display_name}")
                await csatorna.send(embed=embed)
            else:
                # Sima szöveges üzenet
                await csatorna.send(uzenet)

            await interaction.response.send_message(
                f"✅ Az üzenet sikeresen elküldve a(z) {csatorna.mention} csatornába!", 
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ A botnak nincs jogosultsága üzenetet küldeni a(z) {csatorna.mention} csatornába!", 
                ephemeral=True
            )
        except Exception as exc:
            log.error("Hiba a /sendmessage futtatásakor: %s", exc)
            await interaction.response.send_message(
                f"❌ Hiba történt az üzenet küldése közben: `{exc}`", 
                ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SendMessageCog(bot))
