"""General-purpose Discord slash commands (ping, echo, dice, whoami, halt)."""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import CommandPermissionError, check_command_permission


class GeneralCog(commands.Cog):
    """Simple utility slash commands available to all users.

    Args:
        discord_bot: The bot instance (used by ``halt`` to shut down).
    """

    def __init__(self, discord_bot: commands.Bot) -> None:
        super().__init__()
        self._discord_bot = discord_bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce config-driven command permission for every slash command."""
        assert interaction.command is not None
        allowed, msg = await check_command_permission(
            interaction, interaction.command.name
        )
        if not allowed:
            raise CommandPermissionError(msg)
        return True

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle CommandPermissionError raised by interaction_check."""
        error = getattr(error, "original", error)
        if isinstance(error, CommandPermissionError):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

    @app_commands.command(name="ping", description="Return the current server time.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            time.asctime(time.localtime(time.time()))
        )

    @app_commands.command(name="echo", description="Echo back the provided text.")
    @app_commands.describe(s="The text to echo back")
    async def echo(self, interaction: discord.Interaction, s: str = "echo"):
        await interaction.response.send_message(s)

    @app_commands.command(
        name="dice", description="Roll dice with the given number of faces."
    )
    @app_commands.describe(faces='Dice faces, e.g. "6" or "6 20 100"')
    async def dice(self, interaction: discord.Interaction, faces: str = "6"):
        args = faces.split()
        results: list[int] = []
        for i in args:
            if not (i.isdigit() and int(i) >= 1):
                await interaction.response.send_message(
                    f"Invalid argument: {i}", ephemeral=True
                )
                return
            results.append(random.randint(1, int(i)))
        lines = [f"\U0001f3b2: {r}" for r in results]
        if len(results) > 1:
            lines.append(f"\u603b\u548c: {sum(results)}")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="whoami", description="Show your Discord display name.")
    async def whoami(self, interaction: discord.Interaction):
        await interaction.response.send_message(interaction.user.display_name)

    @app_commands.command(name="halt", description="Shut down the bot.")
    async def halt(self, interaction: discord.Interaction):
        await interaction.response.send_message("Shutting down...")
        await self._discord_bot.close()
