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
import yaml

_config_cache: dict[str, dict] = {}
_dotenv_cache: dict[str, str] = {}
_dotenv_loaded = False


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
        raise ValueError(f"Missing {key} in .env")
    return v


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _validate_base_prompt(cfg: dict) -> None:
    if "base" not in cfg:
        raise ConfigParseError("Missing 'base' key")
    if not cfg["base"]:
        raise ConfigParseError("base prompt is empty")


def _validate_character_prompt(cfg: dict) -> None:
    if not cfg:
        raise ConfigParseError("No content found")
    # allow empty profile


def _validate_bot(cfg: dict) -> None:
    if "defaults" not in cfg:
        raise ConfigParseError("Missing 'defaults' section")
    defaults = cfg["defaults"]
    for key in ("llm_profile", "prompt_profile"):
        if key not in defaults:
            raise ConfigParseError(f"Missing 'defaults.{key}'")

    default_llm = defaults["llm_profile"]
    default_prompt = defaults["prompt_profile"]

    if default_llm not in get_llm_profile_names():
        raise ConfigParseError(
            f"Default llm_profile '{default_llm}' not found in providers config"
        )
    if default_prompt not in get_character_prompt_names():
        raise ConfigParseError(
            f"Default prompt_profile '{default_prompt}' not found in character config"
        )

    wl = cfg.get("whitelist_guilds", [])
    if not isinstance(wl, list):
        raise ConfigParseError("'whitelist_guilds' must be a list")
    for gid in wl:
        if not isinstance(gid, int):
            raise ConfigParseError(f"whitelist_guilds: {gid} must be an integer")


def _validate_llm_providers(cfg: dict) -> None:
    if not cfg:
        raise ConfigParseError("No providers configured")
    for name, provider in cfg.items():
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
    return set(load_character_prompt_config().keys())


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
        for profile_name in provider_cfg.get("profiles", {}):
            keys.add(f"{provider_name}-{profile_name}")
    return keys


# ---------------------------------------------------------------------------
# Shortcuts (for callers that only need one value)
# ---------------------------------------------------------------------------


def get_base_prompt() -> str:
    """Return the base prompt from ``llm_base_prompt.yaml``."""
    return load_base_prompt_config()["base"]


def get_default_llm_profile() -> str:
    """Return the default LLM profile from ``bot.yaml``."""
    return load_bot_config()["defaults"]["llm_profile"]


def get_default_prompt_profile() -> str:
    """Return the default character prompt profile from ``bot.yaml``."""
    return load_bot_config()["defaults"]["prompt_profile"]


def get_whitelist_guilds() -> set[int]:
    """Return the set of allowed guild IDs from ``bot.yaml``.

    An empty set means no restriction (all guilds are allowed).
    """
    return set[int](load_bot_config().get("whitelist_guilds", []))


def get_api_key(provider_name: str) -> str:
    return _load_from_dotenv(provider_name.upper() + "_API_KEY")


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
