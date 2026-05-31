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