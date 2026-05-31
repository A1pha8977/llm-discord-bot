import yaml


def load_prompt_yaml(path: str = "config/llm_base_prompt.yaml") -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in {path}:\n{e}")
    return config
