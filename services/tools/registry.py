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

_VALID_PARAM_KEYS: dict[str, frozenset[str]] = {
    "description":       frozenset({"string", "integer", "number", "boolean", "array"}),
    "type":              frozenset({"string", "integer", "number", "boolean", "array"}),
    "enum":              frozenset({"string", "integer", "number"}),
    "minimum":           frozenset({"integer", "number"}),
    "maximum":           frozenset({"integer", "number"}),
    "exclusiveMinimum":  frozenset({"integer", "number"}),
    "exclusiveMaximum":  frozenset({"integer", "number"}),
    "multipleOf":        frozenset({"integer", "number"}),
    "const":             frozenset({"string", "integer", "number", "boolean"}),
    "default":           frozenset({"string", "integer", "number", "boolean", "array"}),
    "items":             frozenset({"array"}),
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
        tool_description: str = "",
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

            self._tools[_name] = (func, {"description": tool_description, "params": params})
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

        lines = result.strip().splitlines()
        truncated_lines = [
            line[:147] + "..." if len(line) > 150 else line
            for line in lines[:5]
        ]
        truncated = "\n".join(truncated_lines)
        if len(lines) > 5:
            truncated += "\n... [truncated]"
        _logger.info('Tool "%s" result: %s', name, truncated)
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
        """Validate that *declared* names match *fn*'s signature, then
        delegate each ``dict``-style entry to
        :meth:`_validate_param_schema`."""
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

        for param_name, param_desc in declared.items():
            if isinstance(param_desc, dict):
                ToolRegistry._validate_param_schema(
                    name, param_name, sig.parameters[param_name], param_desc
                )

    @staticmethod
    def _validate_param_schema(
        name: str,
        param_name: str,
        param: inspect.Parameter,
        param_desc: dict,
    ) -> None:
        """Validate a ``dict``-style parameter description.

        Checks performed:

        * ``"description"`` key is present.
        * ``"default"`` is present if and only if the function parameter
          has a default value.
        * An explicit ``"type"`` must match the Python annotation when
          the annotation maps to a known JSON Schema type.
        * Every key is a known JSON Schema key.
        * Every key is allowed for the parameter's declared type.
        """
        if "description" not in param_desc:
            raise ValueError(
                f"Tool '{name}': param '{param_name}' dict must "
                f"include 'description' key"
            )

        has_schema_default = "default" in param_desc
        has_func_default = param.default is not inspect.Parameter.empty
        if has_schema_default and not has_func_default:
            raise ValueError(
                f"Tool '{name}': param '{param_name}' declares 'default' "
                f"in schema but function signature has no default value"
            )
        if has_func_default and not has_schema_default:
            raise ValueError(
                f"Tool '{name}': param '{param_name}' has a function "
                f"default but schema does not declare 'default'"
            )

        annotation_type = _TYPE_MAP.get(param.annotation)
        explicit_type = param_desc.get("type")
        if annotation_type is not None and explicit_type is not None:
            if explicit_type != annotation_type:
                raise ValueError(
                    f"Tool '{name}': param '{param_name}' declares "
                    f"'type': '{explicit_type}' in schema but function "
                    f"annotation maps to '{annotation_type}'"
                )
        
        json_type = param_desc.get("type") or _TYPE_MAP.get(
            param.annotation, "string"
        )
        for key in param_desc:
            if key == "type":
                continue
            if key not in _VALID_PARAM_KEYS:
                raise ValueError(
                    f"Tool '{name}': param '{param_name}' has "
                    f"unknown key '{key}'"
                )
            if json_type not in _VALID_PARAM_KEYS[key]:
                raise ValueError(
                    f"Tool '{name}': key '{key}' not allowed for "
                    f"type '{json_type}' in param '{param_name}'"
                )

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
            desc = descriptions[pname]
            if isinstance(desc, str):
                properties[pname] = {"type": json_type, "description": desc}
            else:
                properties[pname] = {
                    "type": desc.get("type", json_type),
                    **{k: v for k, v in desc.items()
                       if k != "type" and not (k == "default" and v is None)},
                }
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
