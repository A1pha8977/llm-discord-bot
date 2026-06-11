"""Unit tests for ToolRegistry, _get_json_type, and tool execution."""

import unittest
from services.tools.registry import ToolRegistry, _get_json_type


class TestGetJsonType(unittest.TestCase):
    """Tests for _get_json_type type resolution."""

    def test_primitive_types(self):
        self.assertEqual(_get_json_type(int), "integer")
        self.assertEqual(_get_json_type(str), "string")
        self.assertEqual(_get_json_type(float), "number")
        self.assertEqual(_get_json_type(bool), "boolean")

    def test_generic_list(self):
        self.assertEqual(_get_json_type(list[str]), "array")

    def test_unsupported_type(self):
        self.assertIsNone(_get_json_type(bytes))


class TestToolRegistry(unittest.TestCase):
    """Tests for ToolRegistry register, execute, and schema generation."""

    def setUp(self):
        self.registry = ToolRegistry()

    # --- register ---

    def test_register_success(self):
        @self.registry.register(
            name="add",
            tool_description="Add two numbers",
            params={"a": "first number", "b": "second number"},
        )
        def add(a: int, b: int) -> str:
            return str(a + b)

        self.assertIn("add", self.registry)

    def test_register_default_name(self):
        @self.registry.register(
            tool_description="Say hello",
            params={},
        )
        def hello() -> str:
            return "hi"

        self.assertIn("hello", self.registry)

    def test_register_duplicate_raises(self):
        @self.registry.register(name="dup", tool_description="a", params={})
        def dup_a() -> str:
            return "a"

        with self.assertRaises(ValueError):

            @self.registry.register(name="dup", tool_description="b", params={})
            def dup_b() -> str:
                return "b"

    def test_register_disabled(self):
        @self.registry.register(
            name="disabled",
            tool_description="x",
            params={},
            enabled=False,
        )
        def disabled() -> str:
            return "off"

        self.assertNotIn("disabled", self.registry)

    def test_register_unknown_param(self):
        with self.assertRaises(ValueError):

            @self.registry.register(
                name="bad",
                tool_description="x",
                params={"fake": "not a real param"},
            )
            def bad() -> str:
                return "x"

    def test_register_missing_param(self):
        with self.assertRaises(ValueError):

            @self.registry.register(
                name="bad",
                tool_description="x",
                params={},
            )
            def bad(x: int) -> str:
                return str(x)

    def test_register_unsupported_type(self):
        with self.assertRaises(ValueError):

            @self.registry.register(
                name="bad",
                tool_description="x",
                params={"x": "some bytes"},
            )
            def bad(x: bytes) -> str:
                return "x"

    def test_register_optional_param_rejected(self):
        with self.assertRaises(ValueError):

            @self.registry.register(
                name="bad",
                tool_description="x",
                params={"x": "an optional int"},
            )
            def bad(x: int | None) -> str:
                return str(x)

    def test_register_rich_params_validation(self):
        """dict params must include 'description' key."""
        with self.assertRaises(ValueError):

            @self.registry.register(
                name="bad",
                tool_description="x",
                params={"x": {"type": "integer"}},
            )
            def bad(x: int) -> str:
                return str(x)

    # --- execute ---

    def test_execute_success(self):
        @self.registry.register(
            name="mul",
            tool_description="Multiply",
            params={"a": "left", "b": "right"},
        )
        def mul(a: int, b: int) -> str:
            return str(a * b)

        result = self.registry.execute("mul", "call_1", {"a": 3, "b": 4})
        self.assertEqual(result["role"], "tool")
        self.assertEqual(result["tool_call_id"], "call_1")
        self.assertEqual(result["content"], "12")

    def test_execute_unknown_tool(self):
        result = self.registry.execute("nope", "call_1", {})
        self.assertIn("Error: unknown tool", result["content"])

    def test_execute_invalid_args(self):
        @self.registry.register(
            name="sub",
            tool_description="Subtract",
            params={"a": "left", "b": "right"},
        )
        def sub(a: int, b: int) -> str:
            return str(a - b)

        result = self.registry.execute("sub", "call_1", {"a": 1})
        self.assertIn("Error: invalid arguments", result["content"])

    # --- schema ---

    def test_to_openai_schema_non_strict(self):
        @self.registry.register(
            name="echo",
            tool_description="Echo text",
            params={"text": "text to echo"},
        )
        def echo(text: str) -> str:
            return text

        schema = self.registry.to_openai_schema(strict=False)
        self.assertEqual(len(schema), 1)
        func = schema[0]["function"]
        self.assertEqual(func["name"], "echo")
        self.assertEqual(func["description"], "Echo text")
        self.assertNotIn("strict", func)
        params = func["parameters"]
        self.assertEqual(params["type"], "object")
        self.assertIn("text", params["properties"])
        self.assertEqual(params["properties"]["text"]["type"], "string")
        self.assertNotIn("additionalProperties", params)

    def test_to_openai_schema_strict(self):
        @self.registry.register(
            name="echo",
            tool_description="Echo text",
            params={"text": "text to echo"},
        )
        def echo(text: str) -> str:
            return text

        schema = self.registry.to_openai_schema(strict=True)
        func = schema[0]["function"]
        self.assertTrue(func["strict"])
        params = func["parameters"]
        self.assertFalse(params["additionalProperties"])
        self.assertIn("text", params["required"])


if __name__ == "__main__":
    unittest.main()
