import inspect
import logging
from collections.abc import Callable

_logger = logging.getLogger(__name__)

_TYPE_MAP = {
    int: "integer",
    str: "string",
    float: "number",
    bool: "boolean",
    list: "array",
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
        params: dict[str, str | dict] | None = None,
        enabled: bool = True,
    ):
        """Decorator: register a function as a callable tool.

        Args:
            name: Tool name (defaults to function name).
            description: Human-readable tool description for the LLM.
            params: Map of parameter names to descriptions (``str``) or
                rich JSON Schema partials (``dict``).  A rich partial
                must include a ``"description"`` key and may carry extra
                constraints (``enum``, ``minimum``, ``maximum``,
                ``items`` for arrays, etc.).  Declared names must match
                the function's signature exactly.
        """
        if params is None:
            params = {}

        def wrapper(func: Callable[..., object]):
            if not enabled:
                return func
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

        _logger.info('Calling tool "%s" with args: %s', name, args)
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

    def to_openai_schema(self, *, strict: bool = False) -> list[dict]:
        """Return the OpenAI ``tools`` array for all registered tools.

        Args:
            strict: When ``True``, emit DeepSeek strict-mode schemas
                (``"strict": true`` on every function,
                ``"additionalProperties": false``, and all parameters
                marked as required).
        """
        result: list[dict] = []
        for name, (fn, info) in self._tools.items():
            func_def: dict = {
                "name": name,
                "description": info["description"],
                "parameters": self._build_openai_params(
                    fn, info["params"], strict=strict
                ),
            }
            if strict:
                func_def["strict"] = True
            result.append({"type": "function", "function": func_def})
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # --- Internal ---

    @staticmethod
    def _check_params(name: str, fn: Callable, declared: dict[str, str | dict]) -> None:
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

        for pname, desc in declared.items():
            if isinstance(desc, dict) and "description" not in desc:
                raise ValueError(
                    f"Tool '{name}': param '{pname}' dict must include "
                    f"'description' key"
                )

    @staticmethod
    def _build_param_schema(desc: str | dict, fallback_type: str = "string") -> dict:
        """Build a JSON Schema property dict from a simple string or rich
        ``dict`` partial.

        When *desc* is a ``str`` the result is ``{"type": fallback_type,
        "description": desc}``.

        When *desc* is a ``dict`` the keys are merged into the result
        (``type`` defaults to *fallback_type* unless overridden).
        Supported extra keys: ``enum``, ``minimum``, ``maximum``,
        ``exclusiveMinimum``, ``exclusiveMaximum``, ``multipleOf``,
        ``const``, ``default``, ``items``.
        """
        if isinstance(desc, str):
            return {"type": fallback_type, "description": desc}

        schema: dict = {"type": desc.get("type", fallback_type)}
        for key in (
            "description",
            "enum",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
            "const",
            "default",
            "items",
        ):
            if key in desc:
                schema[key] = desc[key]
        return schema

    @staticmethod
    def _build_openai_params(
        fn: Callable,
        descriptions: dict[str, str | dict],
        *,
        strict: bool = False,
    ) -> dict:
        sig = inspect.signature(fn)
        properties: dict = {}
        required: list[str] = []

        for pname, param in sig.parameters.items():
            json_type = _TYPE_MAP.get(param.annotation, "string")
            properties[pname] = ToolRegistry._build_param_schema(
                descriptions[pname], fallback_type=json_type
            )
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        result: dict = {
            "type": "object",
            "properties": properties,
            "required": required,
        }
        if strict:
            result["required"] = list(properties.keys())
            result["additionalProperties"] = False
        return result


tool_registry = ToolRegistry()
