import importlib
from pathlib import Path
from services.tools.registry import ToolRegistry, tool_registry

# Auto-discover and register all tool modules (excludes __init__, registry, and _-prefixed files)
_tools_dir = Path(__file__).parent
for _f in _tools_dir.glob("*.py"):
    if _f.stem not in ("__init__", "registry") and not _f.stem.startswith("_"):
        importlib.import_module(f"services.tools.{_f.stem}")
