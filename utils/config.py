import yaml


class ConfigError(Exception):
    """Base exception for config loading errors."""


class ConfigNotFoundError(ConfigError):
    """Config file not found."""


class ConfigParseError(ConfigError):
    """Config file has invalid format."""


def _load_yaml(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigNotFoundError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise ConfigParseError(f"Invalid YAML in {path}:\n{e}")


def load_base_prompt_config(path: str = "config/llm_base_prompt.yaml") -> dict:
    return _load_yaml(path)


def load_character_prompt_config(
    path: str = "config/llm_character.yaml",
) -> dict:
    return _load_yaml(path)



def load_bot_config(path: str = "config/bot.yaml") -> dict:
    return _load_yaml(path)


def validate_all() -> None:
    """Validate all config files. Called once at startup.

    Raises:
        ConfigParseError: If any config file is missing required keys.
    """
    cfg = load_base_prompt_config()
    if "system" not in cfg:
        raise ConfigParseError("Missing 'system' key in llm_base_prompt.yaml")

    cfg = load_character_prompt_config()
    if not cfg:
        raise ConfigParseError("No content found in llm_character.yaml")

    cfg = load_bot_config()
    if "defaults" not in cfg:
        raise ConfigParseError("Missing 'defaults' section in bot.yaml")
    defaults = cfg["defaults"]
    for key in ("llm_profile", "prompt_profile"):
        if key not in defaults:
            raise ConfigParseError(f"Missing 'defaults.{key}' in bot.yaml")
