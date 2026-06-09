import random

from services.tools.registry import tool_registry


@tool_registry.register(
    "random",
    tool_description="Generate one or more random numbers in range [min_val, max_val]. Use for dice, random selection, draw lots, etc.",
    params={
        "count": {
            "description": "How many random numbers to generate (required)",
            "minimum": 1,
            "maximum": 100,
        },
        "min_val": {
            "description": "Minimal value for each random number (range: min_val to max_val, inclusive)",
            "default": 0,
        },
        "max_val": {
            "description": "Maximum value for each random number (range: min_val to max_val, inclusive)",
        },
    },
)
def random_tool(*, count: int, min_val: int = 0, max_val: int) -> str:
    if count < 1 or count > 100:
        return f"random error: count must be >= 1 and <= 100, got {count}"
    if min_val > max_val:
        return f"random error: min_val must be <= max_val, got min_val={min_val} > max_val={max_val}"
    results = [str(random.randint(min_val, max_val)) for _ in range(count)]
    return ", ".join(results)
