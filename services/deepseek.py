import os

from services.llm import LLMClient


class DeepSeekClient(LLMClient):

    def __init__(self, api_key: str):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )


__CLIENT: DeepSeekClient | None = None


def get_deep_seek_client() -> DeepSeekClient:
    global __CLIENT
    if __CLIENT is None:
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        __CLIENT = DeepSeekClient(key)
    return __CLIENT
