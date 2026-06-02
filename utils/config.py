import yaml


def _load_yaml(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in {path}:\n{e}")


def load_base_prompt_config(path: str = "config/llm_base_prompt.yaml") -> dict:
    return _load_yaml(path)


def load_character_prompt_config(
    path: str = "config/llm_character.yaml",
) -> dict | None:
    try:
        return _load_yaml(path)
    except RuntimeError:
        return None
