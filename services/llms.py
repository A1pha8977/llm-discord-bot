"""LLM client factory."""

import os

import yaml

from services.llm import LLMClient


class LLMClientFactory:
    """Creates all LLMClient instances from a YAML provider config.

    API keys are resolved from ``.env`` via convention:
    ``{PROVIDER}_API_KEY`` (e.g. ``DEEPSEEK_API_KEY``).

    Returns a dict keyed by ``"provider-profile"``::

        {"deepseek-fast": LLMClient(...), "mimo-default": LLMClient(...)}
    """

    @classmethod
    def build(cls, path: str = "config/llm_providers.yaml") -> dict[str, LLMClient]:
        """Build all LLMClient instances from the provider config file."""
        config = cls._load_yaml(path)
        clients: dict[str, LLMClient] = {}
        for provider_name, provider_cfg in config.items():
            api_key = cls._resolve_api_key(provider_name)
            if "base_url" not in provider_cfg:
                raise ValueError(
                    f"Provider '{provider_name}' is missing 'base_url'"
                )
            if "profiles" not in provider_cfg:
                raise ValueError(
                    f"Provider '{provider_name}' is missing 'profiles'"
                )
            base_url = provider_cfg["base_url"]
            for profile_name, profile_cfg in provider_cfg["profiles"].items():
                if "model_name" not in profile_cfg:
                    raise ValueError(
                        f"Provider '{provider_name}' profile '{profile_name}' is missing 'model_name'"
                    )
                key = f"{provider_name}-{profile_name}"
                clients[key] = LLMClient(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=profile_cfg["model_name"],
                    temperature=float(profile_cfg.get("temperature", 0.7)),
                    max_output_tokens=int(profile_cfg.get("max_output_tokens", 300)),
                )
        if not clients:
            raise ValueError(f"No providers found in {path}")
        return clients

    @staticmethod
    def _resolve_api_key(provider_name: str) -> str:
        key = os.getenv(f"{provider_name.upper()}_API_KEY")
        if not key:
            raise ValueError(
                f"Missing {provider_name.upper()}_API_KEY in .env"
            )
        return key

    @staticmethod
    def _load_yaml(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Provider config not found: {path}")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Invalid YAML in {path}:\n{e}")
