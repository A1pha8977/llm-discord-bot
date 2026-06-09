"""Guild whitelist enforcement — automatically leaves non-whitelisted guilds."""

import logging

import discord
from discord.ext import commands

from utils import config

_logger = logging.getLogger(__name__)


class GuildWhitelistCog(commands.Cog):
    """Enforces a server (guild) whitelist for the bot.

    When the bot joins a non-whitelisted guild it immediately leaves.
    On startup it scans all connected guilds and leaves any that are
    not in the whitelist.

    Args:
        discord_bot: The bot instance (used to access guild list).
    """

    def __init__(self, discord_bot: commands.Bot) -> None:
        super().__init__()
        self._bot = discord_bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Leave immediately if the guild is not in the whitelist."""
        whitelist = config.get_whitelist_guilds()
        if not whitelist:
            return
        if guild.id not in whitelist:
            _logger.warning(
                "Leaving non-whitelisted guild '%s' (%d)",
                guild.name,
                guild.id,
            )
            await guild.leave()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Scan all connected guilds and leave any non-whitelisted ones."""
        whitelist = config.get_whitelist_guilds()
        if not whitelist:
            return
        for guild in self._bot.guilds:
            if guild.id not in whitelist:
                _logger.warning(
                    "Leaving non-whitelisted guild '%s' (%d)",
                    guild.name,
                    guild.id,
                )
                await guild.leave()
