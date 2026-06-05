import inspect
from collections.abc import Callable

import logging

_logger = logging.getLogger(__name__)

_TYPE_MAP = {
    int: "integer",
    str: "string",
    float: "number",
    bool: "boolean",
}


class ToolRegistry:
    """Registry of callable tools with OpenAI schema generation."""

    def __init__(self):
        self._tools: dict[str, tuple[Callable[..., object], dict]] = {}
        # key=name → (func, info: {description, params})

    def register(
        self,
        name: str | None = None,
        *,
        description: str = "",
        params: dict[str, str] | None = None,
    ):
        """Decorator: register a function as a callable tool.

        Args:
            name: Tool name (defaults to function name).
            description: Human-readable tool description for the LLM.
            params: Map of parameter names to descriptions.  Must match the
                function's signature exactly.
        """
        if params is None:
            params = {}

        def wrapper(func: Callable[..., object]):
            _name = name or func.__name__
            if _name in self._tools:
                raise ValueError(f"Tool '{_name}' is already registered")

            self._check_params(_name, func, params)

            self._tools[_name] = (func, {"description": description, "params": params})
            return func

        return wrapper

    def execute(self, name: str, tool_call_id: str, args: dict) -> dict:
        """Execute a tool and return an OpenAI-compatible tool response.

        On error, returns a tool response with ``content`` starting with
        ``"Error:"`` so the LLM can read the problem and retry.
        """
        try:
            fn, _ = self._tools[name]
        except KeyError:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Error: unknown tool '{name}'",
            }

        _logger.info("Calling tool %s with args: %s", name, args)
        try:
            sig = inspect.signature(fn)
            bound = sig.bind(**args)
            bound.apply_defaults()
            result = str(fn(**bound.arguments))
        except TypeError as e:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Error: invalid arguments for '{name}': {e}",
            }

        _logger.info("Tool %s result: %s", name, result)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def to_openai_schema(self) -> list[dict]:
        """Return the OpenAI ``tools`` array for all registered tools."""
        result: list[dict] = []
        for name, (fn, info) in self._tools.items():
            func_def: dict = {
                "name": name,
                "description": info["description"],
                "parameters": self._build_openai_params(fn, info["params"]),
            }
            result.append({"type": "function", "function": func_def})
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # --- Internal ---

    @staticmethod
    def _check_params(name: str, fn: Callable, declared: dict[str, str]) -> None:
        sig = inspect.signature(fn)
        func_params = set(sig.parameters.keys())
        declared_set = set(declared.keys())

        extra = declared_set - func_params
        if extra:
            raise ValueError(
                f"Tool '{name}': params declares unknown parameters: {extra}"
            )

        missing = func_params - declared_set
        if missing:
            raise ValueError(
                f"Tool '{name}': missing descriptions for parameters: {missing}"
            )

    @staticmethod
    def _build_openai_params(fn: Callable, descriptions: dict[str, str]) -> dict:
        sig = inspect.signature(fn)
        properties: dict = {}
        required: list[str] = []

        for pname, param in sig.parameters.items():
            json_type = _TYPE_MAP.get(param.annotation, "string")
            properties[pname] = {"type": json_type, "description": descriptions[pname]}
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }


tool_registry = ToolRegistry()
