"""LLM client factory."""

import os

from services.llm import LLMClient
from utils import config

class LLMClientFactory:
    """Creates all LLMClient instances from a YAML provider config.

    API keys are resolved from ``.env`` via convention:
    ``{PROVIDER}_API_KEY`` (e.g. ``DEEPSEEK_API_KEY``).

    Returns a dict keyed by ``"provider-profile"``::

        {"deepseek-fast": LLMClient(...), "mimo-default": LLMClient(...)}
    """

    @classmethod
    def build(cls) -> dict[str, LLMClient]:
        """Build all LLMClient instances from the provider config file."""
        llms_config = config.load_llm_providers_config()
        clients: dict[str, LLMClient] = {}
        for provider_name, provider_cfg in llms_config.items():
            api_key = cls._resolve_api_key(provider_name)
            base_url = provider_cfg["base_url"]
            for profile_name, profile_cfg in provider_cfg["profiles"].items():
                key = f"{provider_name}-{profile_name}"
                clients[key] = LLMClient(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=profile_cfg["model_name"],
                    temperature=float(profile_cfg.get("temperature", 0.7)),
                    max_output_tokens=int(profile_cfg.get("max_output_tokens", 300)),
                )
        return clients

    @staticmethod
    def _resolve_api_key(provider_name: str) -> str:
        key = os.getenv(f"{provider_name.upper()}_API_KEY")
        if not key:
            raise ValueError(
                f"Missing {provider_name.upper()}_API_KEY in .env"
            )
        return key
