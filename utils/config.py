"""Configuration loading & validation — all configuration flows through this module.

Every ``load_*_config()`` function:
* Reads its YAML file **once** (cached in ``_cache``).
* Runs its private ``_validate_*()`` on the **first** access, so malformed
  configs are rejected at startup (``validate_all()`` in ``main.py``).
* Files are identified via `naming convention`_: ``load_{name}_config``.

``validate_all()`` auto-discovers every ``load_*_config`` function — adding a
new loader automatically includes it in startup validation with zero edits
to this function.

-----------
Usage
-----------

.. code-block:: python

    from utils import config

    # Startup (once, in main.py)
    config.validate_all()

    # Anywhere later — returns cached dict
    cfg = config.load_bot_config()
    defaults = cfg["defaults"]


    For API key variables (loaded from ``.env`` instead of YAML), use the
    func:`get_api_key` which appends ``_API_KEY`` to the base name
    and reads from the environment::

        # Reads ``TAVILY_API_KEY`` from .env
        tavily_key = config.get_api_key("tavily")
-----------
Adding a new config file
-----------

1. Write a ``_validate_xxx(cfg: dict) -> None`` function.
2. Write a ``load_xxx_config(path="config/xxx.yaml") -> dict`` function that
   calls ``_load_once(path, validator=_validate_xxx)``.
3. Done — ``validate_all()`` picks it up via naming convention.

Example::

    def _validate_greeting(cfg: dict) -> None:
        if "text" not in cfg:
            raise ConfigParseError("Missing 'text' key")

    def load_greeting_config(path="config/greeting.yaml") -> dict:
        return _load_once(path, validator=_validate_greeting)

No other files need modification.

"""

import os
import sys
from collections.abc import Callable
from types import ModuleType

import dotenv
import logging
import yaml

_config_cache: dict[str, dict] = {}
_dotenv_cache: dict[str, str] = {}
_dotenv_loaded = False
_logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Base exception for config loading errors."""


class ConfigNotFoundError(ConfigError):
    """Config file not found."""


class ConfigParseError(ConfigError):
    """Config file has invalid format."""


def _load_yaml(path: str) -> dict:
    y = None
    try:
        with open(path, encoding="utf-8") as f:
            y = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigNotFoundError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise ConfigParseError(f"Invalid YAML in {path}:\n{e}")
    if not isinstance(y, dict):
        raise ConfigParseError(f"Config file must be a YAML mapping: {path}")
    return y


def _load_once(path: str, *, validator: Callable[[dict], None] | None = None) -> dict:
    if path not in _config_cache:
        cfg = _load_yaml(path)
        if validator is not None:
            validator(cfg)
        _config_cache[path] = cfg
    return _config_cache[path]


def _load_from_dotenv(key: str) -> str:
    global _dotenv_loaded
    if not _dotenv_loaded:
        dotenv.load_dotenv()
        _dotenv_loaded = True
    v = os.getenv(key)
    if v is None:
        raise ValueError(f"{key} not found in environment variables or .env file")
    return v


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# Valid permission level names (order: high → low).
_VALID_PERMISSION_LEVELS = frozenset({"owner", "admin", "user", "guest", "block"})


def _validate_base_prompt(cfg: dict) -> None:
    if "base" not in cfg:
        raise ConfigParseError("Missing 'base' key")
    if not cfg["base"]:
        raise ConfigParseError("base prompt is empty")


def _validate_character_prompt(cfg: dict) -> None:
    if not cfg:
        raise ConfigParseError("No content found")
    if "default_profile" not in cfg:
        raise ConfigParseError("Missing 'default_profile' key")
    dp = cfg["default_profile"]
    if dp not in cfg:
        raise ConfigParseError(
            f"default_profile '{dp}' not found in character profiles"
        )


def _validate_bot(cfg: dict) -> None:
    wl = cfg.get("whitelist_guilds", [])
    if not isinstance(wl, list):
        raise ConfigParseError("'whitelist_guilds' must be a list")
    for gid in wl:
        if not isinstance(gid, int):
            raise ConfigParseError(f"whitelist_guilds: {gid} must be an integer")

    et = cfg.get("enabled_tools")
    if et is not None:
        if not isinstance(et, dict):
            raise ConfigParseError(
                "'enabled_tools' must be a mapping of tool_name: bool"
            )
        for k, v in et.items():
            if not isinstance(v, bool):
                raise ConfigParseError(f"enabled_tools.{k} must be true or false")

    rl = cfg.get("rate_limit")
    if rl is None:
        raise ConfigParseError("Missing 'rate_limit' section")
    if not isinstance(rl, dict):
        raise ConfigParseError("'rate_limit' must be a mapping")
    _validate_rate_limit(rl)

    pl = cfg.get("permission_levels")
    if pl is None:
        raise ConfigParseError("Missing 'permission_levels' section")
    _validate_permission_levels(pl)

    cp = cfg.get("command_permissions")
    if cp is None:
        raise ConfigParseError("Missing 'command_permissions' section")
    _validate_command_permissions(cp)


def _validate_rate_limit(cfg: dict) -> None:
    """Validate the rate_limit section of bot.yaml."""
    max_req = cfg.get("max_requests", 0)
    max_tok = cfg.get("max_tokens", 0)
    if max_req == 0 and max_tok == 0:
        raise ConfigParseError("both max_requests and max_tokens are 0")
    for key in ("max_requests", "max_tokens"):
        val = cfg.get(key, 0)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            raise ConfigParseError(f"'rate_limit.{key}' must be a non-negative integer")
    ws = cfg.get("window_seconds", 3600)
    if not isinstance(ws, (int, float)) or ws <= 0:
        raise ConfigParseError("'rate_limit.window_seconds' must be > 0")
    mc = cfg.get("max_concurrency", 1)
    if not isinstance(mc, int) or isinstance(mc, bool) or mc < 1:
        raise ConfigParseError(
            "'rate_limit.max_concurrency' must be a positive integer"
        )


def _validate_permission_levels(cfg: dict) -> None:
    """Validate the permission_levels section of bot.yaml."""
    users = cfg.get("users")
    if users is None:
        raise ConfigParseError("'permission_levels.users' is required")
    if not isinstance(users, dict):
        raise ConfigParseError("'permission_levels.users' must be a mapping")
    for required_level in sorted(_VALID_PERMISSION_LEVELS):
        if required_level not in users:
            raise ConfigParseError(
                f"'permission_levels.users' must include all five levels; "
                f"missing: '{required_level}'"
            )
    for level_name, user_ids in users.items():
        if level_name not in _VALID_PERMISSION_LEVELS:
            raise ConfigParseError(
                f"'permission_levels.users.{level_name}' is not a valid level "
                f"(expected one of {sorted(_VALID_PERMISSION_LEVELS)})"
            )
        if not isinstance(user_ids, list):
            raise ConfigParseError(
                f"'permission_levels.users.{level_name}' must be a list"
            )
        for uid in user_ids:
            if not isinstance(uid, int) or isinstance(uid, bool):
                raise ConfigParseError(
                    f"'permission_levels.users.{level_name}' "
                    f"contains non-integer value: {uid}"
                )

    # Warn on duplicate user IDs across levels.
    seen: dict[int, str] = {}
    for level_name, user_ids in users.items():
        for uid in user_ids:
            if uid in seen and seen[uid] != level_name:
                _logger.warning(
                    "User ID %d appears in both '%s' and '%s' permission levels",
                    uid,
                    seen[uid],
                    level_name,
                )
            else:
                seen[uid] = level_name

    default = cfg.get("default_level")
    if default is not None:
        if not isinstance(default, str) or default not in _VALID_PERMISSION_LEVELS:
            raise ConfigParseError(
                f"'permission_levels.default_level' must be one of "
                f"{sorted(_VALID_PERMISSION_LEVELS)}, got: {default}"
            )

    min_ctx = cfg.get("min_context_level")
    if min_ctx is not None:
        if not isinstance(min_ctx, str) or min_ctx not in _VALID_PERMISSION_LEVELS:
            raise ConfigParseError(
                f"'permission_levels.min_context_level' must be one of "
                f"{sorted(_VALID_PERMISSION_LEVELS)}, got: {min_ctx}"
            )


def _validate_command_permissions(cfg: dict) -> None:
    """Validate the command_permissions section of bot.yaml."""
    if not isinstance(cfg, dict):
        raise ConfigParseError("'command_permissions' must be a mapping")
    for cmd_name, cmd_cfg in cfg.items():
        if not isinstance(cmd_cfg, dict):
            raise ConfigParseError(
                f"'command_permissions.{cmd_name}' must be a mapping"
            )
        min_level = cmd_cfg.get("min_level")
        if min_level is not None:
            if (
                not isinstance(min_level, str)
                or min_level not in _VALID_PERMISSION_LEVELS
            ):
                raise ConfigParseError(
                    f"'command_permissions.{cmd_name}.min_level' must be one of "
                    f"{sorted(_VALID_PERMISSION_LEVELS)}, got: {min_level}"
                )


def _validate_llm_providers(cfg: dict) -> None:
    if not cfg:
        raise ConfigParseError("No providers configured")
    if "default_profile" not in cfg:
        raise ConfigParseError("Missing 'default_profile' key")
    dp = cfg["default_profile"]
    if not isinstance(dp, str):
        raise ConfigParseError("'default_profile' must be a string")
    for name, provider in cfg.items():
        if name == "default_profile":
            continue
        for field in ("base_url", "profiles"):
            if field not in provider:
                raise ConfigParseError(f"Missing '{field}' for provider '{name}'")
        if not isinstance(provider["base_url"], str):
            raise ConfigParseError(f"'base_url' for provider '{name}' must be a string")
        if not isinstance(provider["profiles"], dict):
            raise ConfigParseError(
                f"'profiles' for provider '{name}' must be a mapping"
            )
        for profile_name, profile in provider["profiles"].items():
            if "model_name" not in profile:
                raise ConfigParseError(
                    f"Missing 'model_name' for '{name}.{profile_name}'"
                )
            if not isinstance(profile["model_name"], str):
                raise ConfigParseError(
                    f"'model_name' for '{name}.{profile_name}' must be a string"
                )
            if "temperature" in profile:
                t = profile["temperature"]
                if not isinstance(t, (int, float)):
                    raise ConfigParseError(
                        f"'temperature' for '{name}.{profile_name}' must be a number"
                    )
                if t < 0.0 or t > 2.0:
                    raise ConfigParseError(
                        f"'temperature' for '{name}.{profile_name}' must be 0.0–2.0"
                    )
            if "max_output_tokens" in profile:
                n = profile["max_output_tokens"]
                if not isinstance(n, int):
                    raise ConfigParseError(
                        f"'max_output_tokens' for '{name}.{profile_name}' must be an integer"
                    )
                if n < 1:
                    raise ConfigParseError(
                        f"'max_output_tokens' for '{name}.{profile_name}' must be >= 1"
                    )
    valid_profiles = set()
    for name, provider in cfg.items():
        if name == "default_profile":
            continue
        for pname in provider.get("profiles", {}):
            valid_profiles.add(f"{name}-{pname}")
    if dp not in valid_profiles:
        raise ConfigParseError(f"default_profile '{dp}' not found in providers")


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_base_prompt_config(path: str = "config/llm_base_prompt.yaml") -> dict:
    return _load_once(path, validator=_validate_base_prompt)


def load_character_prompt_config(
    path: str = "config/llm_character.yaml",
) -> dict:
    return _load_once(path, validator=_validate_character_prompt)


def load_bot_config(path: str = "config/bot.yaml") -> dict:
    return _load_once(path, validator=_validate_bot)


def load_llm_providers_config(
    path: str = "config/llm_providers.yaml",
) -> dict:
    return _load_once(path, validator=_validate_llm_providers)


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def get_character_prompt_names() -> set[str]:
    """All available character prompt profile names."""
    cfg = load_character_prompt_config()
    return {k for k in cfg if k != "default_profile"}


def get_character_prompt_text(profile_name: str | None = None) -> str:
    """Resolved character prompt text for a profile.

    Falls back to ``"default"`` key, then empty string.
    """
    if profile_name is None:
        return ""
    cfg = load_character_prompt_config()
    return cfg.get(profile_name, cfg.get("default", ""))


def get_llm_profile_names() -> set[str]:
    """All available LLM provider-profile keys (e.g. ``deepseek-creative``)."""
    cfg = load_llm_providers_config()
    keys: set[str] = set()
    for provider_name, provider_cfg in cfg.items():
        if provider_name == "default_profile":
            continue
        for profile_name in provider_cfg.get("profiles", {}):
            keys.add(f"{provider_name}-{profile_name}")
    return keys


# ---------------------------------------------------------------------------
# Shortcuts (for callers that only need one value)
# ---------------------------------------------------------------------------


def get_base_prompt() -> str:
    """Return the base prompt from ``llm_base_prompt.yaml``."""
    return load_base_prompt_config()["base"]


def get_provider_configs() -> dict[str, dict]:
    """Return provider configs from ``llm_providers.yaml``, excluding
    metadata keys such as ``default_profile``.
    """
    cfg = load_llm_providers_config()
    return {k: v for k, v in cfg.items() if k != "default_profile"}


def get_default_llm_profile() -> str:
    """Return the default LLM profile from ``llm_providers.yaml``."""
    return load_llm_providers_config()["default_profile"]


def get_default_prompt_profile() -> str:
    """Return the default character prompt profile from
    ``llm_character.yaml``."""
    return load_character_prompt_config()["default_profile"]


def get_whitelist_guilds() -> set[int]:
    """Return the set of allowed guild IDs from ``bot.yaml``.

    An empty set means no restriction (all guilds are allowed).
    """
    return set[int](load_bot_config().get("whitelist_guilds", []))


def get_rate_limit_config() -> dict:
    """Return the rate_limit config dict from bot.yaml."""
    return load_bot_config()["rate_limit"]


def get_permission_levels_config() -> dict:
    """Return the permission_levels config dict from ``bot.yaml``."""
    return load_bot_config()["permission_levels"]


def get_command_permissions_config() -> dict:
    """Return the command_permissions config dict from ``bot.yaml``."""
    return load_bot_config()["command_permissions"]


def get_enabled_tools() -> dict[str, bool]:
    """Return the enabled_tools mapping from ``bot.yaml``.

    Returns an empty dict when the key is absent (meaning: all tools
    enabled).  When present, only tools mapped to ``True`` are enabled.
    """
    et = load_bot_config().get("enabled_tools")
    return et if isinstance(et, dict) else {}


def get_api_key(provider_name: str) -> str:
    return _load_from_dotenv(provider_name.upper() + "_API_KEY")


# Maps tool name to the env var suffix used by get_api_key().
# NOTE: Keys must match the tool name used in ToolRegistry.register().
# Add an entry whenever a new tool requires an API key.
_TOOL_API_KEY_MAP: dict[str, str] = {
    "Tavilysearch": "TAVILY",
}


def validate_tool_api_keys() -> None:
    """Validate API keys only for tools that are currently enabled.

    Skips tools disabled via ``enabled_tools`` in ``bot.yaml``.
    Raises ``ValueError`` when an enabled tool's API key is missing
    from ``.env``, with the tool name included in the message.
    """
    enabled = get_enabled_tools()
    for tool_name, provider_name in _TOOL_API_KEY_MAP.items():
        # enabled is empty → all tools enabled → check all
        # enabled is non-empty → only check tools with True
        if not enabled or enabled.get(tool_name) is True:
            try:
                get_api_key(provider_name)
            except ValueError as e:
                raise ValueError(f"Tool '{tool_name}' is enabled but {e}") from e


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def validate_all() -> None:
    """Validate all config files.  Auto-discovers every ``load_*_config``.

    Adding a new ``load_xxx_config(…)`` includes it automatically — no edits
    needed here.
    """
    module: ModuleType = sys.modules[__name__]
    for name in sorted(dir(module)):
        if name.startswith("load_") and name.endswith("_config"):
            getattr(module, name)()
    validate_tool_api_keys()
