import os

from services.llm import LLMClient


class DeepSeekClient(LLMClient):

    def __init__(self, api_key: str, *,
        model_name = "deepseek-v4-flash",
        temperature = 0.7,
        max_output_tokens =  300,
        response_format = None
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            model_name= model_name,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format=response_format
        )


__CLIENT: DeepSeekClient | None = None


def get_deep_seek_client() -> DeepSeekClient:
    global __CLIENT
    if __CLIENT is None:
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        __CLIENT = DeepSeekClient(key, model_name="deepseek-v4-flash", max_output_tokens=10000, response_format={'type': 'json_object'})
    return __CLIENT
