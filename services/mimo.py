from services.llm import LLMClient


class MimoClient(LLMClient):

    def __init__(self, api_key: str, *,
        model_name = "mimo-v2.5-pro",
        temperature = 0.7,
        max_output_tokens =  300,
        response_format = None
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://api.xiaomimimo.com/v1",
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
        )
