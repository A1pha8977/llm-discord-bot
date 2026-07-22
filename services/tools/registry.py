import inspect
import logging
from collections.abc import Callable
from types import UnionType
from typing import Union, cast, get_origin

from utils import config

_logger = logging.getLogger(__name__)

_TYPE_MAP = {
    int: "integer",
    str: "string",
    float: "number",
    bool: "boolean",
    list: "array",
}

_VALID_PARAM_KEYS: dict[str, frozenset[str]] = {
    "description": frozenset({"string", "integer", "number", "boolean", "array"}),
    "type": frozenset({"string", "integer", "number", "boolean", "array"}),
    "enum": frozenset({"string", "integer", "number"}),
    "minimum": frozenset({"integer", "number"}),
    "maximum": frozenset({"integer", "number"}),
    "exclusiveMinimum": frozenset({"integer", "number"}),
    "exclusiveMaximum": frozenset({"integer", "number"}),
    "multipleOf": frozenset({"integer", "number"}),
    "const": frozenset({"string", "integer", "number", "boolean"}),
    "default": frozenset({"string", "integer", "number", "boolean", "array"}),
    "items": frozenset({"array"}),
}


def _get_json_type(annotation: type) -> str | None:
    """Resolve a Python type annotation to a JSON Schema type string.

    Handles generic types like ``list[str]`` by resolving the
    origin.  ``Optional``, ``Union`` types, and complex unions
    return ``None`` — ``anyOf`` schemas are intentionally not
    supported.
    """
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return None
    if origin is not None:
        return _TYPE_MAP.get(origin)
    return _TYPE_MAP.get(annotation)


class ToolRegistry:
    """Registry of callable tools with OpenAI/DeepSeek schema generation.

    Supported parameter types: ``int``, ``str``, ``float``, ``bool``, ``list``.

    Complex union types (``str | int``), ``Optional``, and
    ``anyOf`` schemas are intentionally not supported.
    """

    def __init__(self):
        self._tools: dict[str, tuple[Callable[..., object], dict]] = {}
        # key=name → (func, info: {description, params})
        self._enabled_tools: dict[str, bool] | None = None
        # None = no filter (all enabled); non-empty dict = only True-valued keys enabled

    def set_enabled_tools(self, enabled_dict: dict[str, bool]) -> None:
        """Apply a tool enable/disable filter from config.

        When *enabled_dict* is non-empty, only tools whose name maps to
        ``True`` are considered enabled.  Tools not in the dict or mapped
        to ``False`` are excluded from schema output and will be rejected
        at execution time.

        Args:
            enabled_dict: Mapping of tool name to bool, e.g.
                ``{"random": True, "time": False}``.
        """
        self._enabled_tools = enabled_dict

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
            tool_description: Human-readable tool description for the LLM.
            params: Map of parameter names to descriptions (``str``) or
                rich JSON Schema partials (``dict``).  A rich partial
                must include a ``"description"`` key and may carry extra
                constraints (``enum``, ``minimum``, ``maximum``,
                ``items`` for arrays, etc.).  ``anyOf`` is not supported.
                Declared names must match the function's signature
                exactly.
            enabled: If ``False``, return the function unchanged without
                registering it (default ``True``).
        """
        if params is None:
            params = {}

        def wrapper(func: Callable[..., object]):
            if not enabled:
                return func
            _name = name or func.__name__
            if _name in self._tools:
                raise ValueError(f"Tool '{_name}' is already registered")

            # Normalize str values to dict for uniform validation and schema generation.
            for k, v in params.items():
                if isinstance(v, str):
                    params[k] = {"description": v}

            self._check_params(_name, func, cast(dict[str, dict], params))

            self._tools[_name] = (
                func,
                {"description": tool_description, "params": params},
            )
            return func

        return wrapper

    def execute(self, name: str, tool_call_id: str, args: dict) -> dict:
        """Execute a tool and return an OpenAI-compatible tool response.

        On error, returns a tool response with ``content`` starting with
        ``"Error:"`` so the LLM can read the problem and retry.
        """
        if self._enabled_tools is not None and self._enabled_tools.get(name) is not True:
            _logger.error(
                'LLM attempted to call disabled tool "%s" with args: %s', name, args
            )
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Error: unknown tool '{name}'",
            }

        try:
            fn, _ = self._tools[name]
        except KeyError:
            _logger.error('Calling unknown tool "%s" with args: %s', name, args)
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
            _logger.error('Calling tool "%s" with unexpected args: %s', name, args)
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Error: invalid arguments for '{name}': {e}",
            }
        except Exception:
            _logger.error('Tool "%s" execution failed', name, exc_info=True)
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"Error: tool '{name}' execution failed",
            }

        lines = result.strip().splitlines()
        truncated_lines = [
            line[:147] + "..." if len(line) > 150 else line for line in lines[:5]
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
            strict: When ``True``, emit strict-mode schemas
                (``"strict": true`` on every function,
                ``"additionalProperties": false``, and all parameters
                marked as required).
        """
        result: list[dict] = []
        for name, (fn, info) in self._tools.items():
            if self._enabled_tools is not None and self._enabled_tools.get(name) is not True:
                continue
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
        if self._enabled_tools is not None and self._enabled_tools.get(name) is not True:
            return False
        return name in self._tools

    # --- Internal ---

    @staticmethod
    def _check_params(name: str, fn: Callable, declared: dict[str, dict]) -> None:
        """Validate that *declared* names match *fn*'s signature and
        all parameter types are supported.  Delegates each
        ``dict``-style entry to :meth:`_validate_param_schema`."""
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

        for param_name, param in sig.parameters.items():
            ToolRegistry._validate_param_schema(
                name, param_name, param, declared[param_name]
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

        annotation_type = _get_json_type(param.annotation)
        explicit_type = param_desc.get("type")
        if annotation_type is not None and explicit_type is not None:
            if explicit_type != annotation_type:
                raise ValueError(
                    f"Tool '{name}': param '{param_name}' declares "
                    f"'type': '{explicit_type}' in schema but function "
                    f"annotation maps to '{annotation_type}'"
                )

        json_type = param_desc.get("type") or _get_json_type(param.annotation)
        if json_type is None:
            hint = (
                " Optional types are not supported."
                if get_origin(param.annotation) in (Union, UnionType)
                else ""
            )
            raise ValueError(
                f"Tool '{name}': param '{param_name}' has unsupported type"
                f" '{param.annotation}'."
                f" Supported: int, str, float, bool, list.{hint}"
            )
        for key in param_desc:
            if key == "type":
                continue
            if key not in _VALID_PARAM_KEYS:
                raise ValueError(
                    f"Tool '{name}': param '{param_name}' has unknown key '{key}'"
                )
            if json_type not in _VALID_PARAM_KEYS[key]:
                raise ValueError(
                    f"Tool '{name}': key '{key}' not allowed for "
                    f"type '{json_type}' in param '{param_name}'"
                )

    @staticmethod
    def _build_openai_params(
        fn: Callable,
        param_specs: dict[str, dict],
        *,
        strict: bool = False,
    ) -> dict:
        """Build the ``parameters`` object for an OpenAI tool schema.

        Args:
            fn: The registered tool function.
            param_specs: Map of parameter names to dict partials
                carrying constraints (``enum``, ``minimum``, etc.).
            strict: When ``True``, all properties are marked required
                and ``additionalProperties`` is set to ``false``.

        Returns:
            A ``{"type": "object", "properties": {...},
            "required": [...]}`` dict.
        """
        sig = inspect.signature(fn)
        properties: dict = {}
        required: list[str] = []

        for pname, param in sig.parameters.items():
            json_type = _get_json_type(param.annotation)
            assert json_type is not None, (
                f"Internal: param '{pname}' has unresolved JSON type"
            )
            desc = param_specs[pname]
            properties[pname] = {
                "type": desc.get("type", json_type),
                **{k: v for k, v in desc.items() if k != "type"},
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

_enabled = config.get_enabled_tools()
if _enabled:
    tool_registry.set_enabled_tools(_enabled)