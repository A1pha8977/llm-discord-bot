"""Config-driven command permission enforcement.

This module reads ``permission_levels`` and ``command_permissions`` from
``config/bot.yaml`` and provides a single entry point
:func:`check_command_permission` that cogs call via their
``interaction_check`` hook.

-----------
Concepts
-----------
**Permission levels** (ordered high → low):

======== ===== ============================================
Level    Value Description
======== ===== ============================================
owner    4     Top-level; equivalent to bot application owner
admin    3     Server administrators
user     2     Trusted regular users
guest    1     Default for unrecognized users
block    0     Explicitly banned — overrides everything
======== ===== ============================================

**Block priority**: if a user ID appears in the ``block`` list they are
denied **regardless** of any other level assignment.

**Default level**: users not listed in any level receive the
``default_level`` from config.

**Default command min_level**: commands not listed in
``command_permissions`` default to ``guest`` (everyone allowed).

-----------
Usage
-----------

.. code-block:: python

    from utils.permissions import check_command_permission, CommandPermissionError

    class MyCog(commands.Cog):
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            allowed, msg = await check_command_permission(
                interaction, interaction.command.name
            )
            if not allowed:
                raise CommandPermissionError(msg)
            return True

        async def cog_app_command_error(self, interaction, error):
            error = getattr(error, 'original', error)
            if isinstance(error, CommandPermissionError):
                await interaction.response.send_message(str(error), ephemeral=True)
                return
"""

import logging
from typing import NamedTuple

import discord
from discord import app_commands

from utils import config

_logger = logging.getLogger(__name__)


class CommandPermissionError(app_commands.CheckFailure):
    """Raised when a user lacks the required permission level for a command.

    The message describes which level is needed.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class PermissionLevel(NamedTuple):
    """A named permission level with an integer value for comparisons."""

    name: str
    value: int


# Ordered high → low so that iteration yields the highest level first.
_ALL_LEVELS: tuple[PermissionLevel, ...] = (
    PermissionLevel("owner", 4),
    PermissionLevel("admin", 3),
    PermissionLevel("user", 2),
    PermissionLevel("guest", 1),
    PermissionLevel("block", 0),
)

# Fast lookups.
_NAME_TO_VALUE: dict[str, int] = {lv.name: lv.value for lv in _ALL_LEVELS}
_VALID_NAMES: frozenset[str] = frozenset(_NAME_TO_VALUE)


def _resolve_user_level(levels_cfg: dict, user_id: int) -> str:
    """Determine a user's effective permission level from config.

    **Block** is checked first and wins unconditionally.  Otherwise the
    first matching level in order (owner → admin → user → guest) is
    returned.  Falls back to ``default_level``.

    Args:
        levels_cfg: The ``permission_levels`` dict from ``bot.yaml``.
        user_id: The Discord user snowflake ID to look up.

    Returns:
        The level name string (e.g. ``"admin"``).
    """
    users = levels_cfg["users"]
    default = levels_cfg.get("default_level", "guest")

    # Block takes absolute priority.
    if user_id in users["block"]:
        return "block"

    for lv in _ALL_LEVELS:
        if lv.name == "block":
            continue  # already checked above
        if user_id in users[lv.name]:
            return lv.name

    return default


def _get_command_min_level(cmd_permissions: dict, command_name: str) -> str:
    """Return the min_level for *command_name*, defaulting to ``"guest"``."""
    cmd_cfg = cmd_permissions.get(command_name)
    if isinstance(cmd_cfg, dict):
        return cmd_cfg.get("min_level", "guest")
    return "guest"


async def check_command_permission(
    interaction: discord.Interaction,
    command_name: str,
) -> tuple[bool, str]:
    """Check whether *interaction.user* may invoke *command_name*.

    Called from a Cog's ``interaction_check`` hook **before** the
    command body runs.

    Args:
        interaction: The incoming Discord interaction.
        command_name: The slash-command name (e.g. ``"halt"``).

    Returns:
        A ``(allowed, message)`` tuple.  When ``allowed`` is ``False``,
        *message* is a human-readable reason for the denial.
    """
    levels_cfg = config.get_permission_levels_config()
    cmd_perms_cfg = config.get_command_permissions_config()

    user_id = interaction.user.id
    user_level = _resolve_user_level(levels_cfg, user_id)

    # Blocked users are denied immediately.
    if user_level == "block":
        return False, "You are blocked from using this bot."

    # Resolve command's required minimum level.
    min_level = _get_command_min_level(cmd_perms_cfg, command_name)

    user_value = _NAME_TO_VALUE.get(user_level)
    min_value = _NAME_TO_VALUE.get(min_level)

    if user_value is None or min_value is None:
        _logger.error(
            "Unknown permission level: user=%s min=%s",
            user_level,
            min_level,
        )
        return False, "Internal permission configuration error."

    if user_value >= min_value:
        return True, ""

    return False, (
        f"You need **{min_level}** permission or higher to use "
        f"`/{command_name}`.  Your level: **{user_level}**."
    )


def check_context_permission(user_id: int) -> bool:
    """Return ``True`` if *user_id* meets ``min_context_level``.

    Called from ``on_message`` to silently ignore messages from users
    below the configured context participation threshold.

    Args:
        user_id: The Discord user snowflake ID.
    """
    levels_cfg = config.get_permission_levels_config()
    user_level = _resolve_user_level(levels_cfg, user_id)
    if user_level == "block":
        return False

    min_ctx = levels_cfg.get("min_context_level", "guest")
    return _NAME_TO_VALUE[user_level] >= _NAME_TO_VALUE[min_ctx]
