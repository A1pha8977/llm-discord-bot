# Side-effect imports — register built-in tools via decorators
import services.tools.random_tool  # noqa: F401
import services.tools.tavily_search  # noqa: F401
import services.tools.time_tool  # noqa: F401
import services.tools.extract_tool  # noqa: F401
from services.tools.registry import ToolRegistry, tool_registry
