import random

from services.tools.registry import tool_registry


@tool_registry.register(
    "random",
    description="Generate one or more random numbers in range [0, max_val]. Use for dice, random selection, draw lots, etc.",
    params={
        "count": {
            "description": "How many random numbers to generate (required)",
            "minimum": 1,
            "maximum": 100,
        },
        "max_val": {
            "description": "Maximum value for each random number (range: 0 to max_val, inclusive)",
            "default": 6,
            "minimum": 1,
        },
    },
)
def random_tool(count: int, max_val: int = 6) -> str:
    if count < 1 or count > 100:
        return f"random_tool error: count must be >= 1 and <= 100, got {count}"
    if max_val < 1:
        return f"random_tool error: max_val must be >= 1, got {max_val}"
    results = [str(random.randint(0, max_val)) for _ in range(count)]
    return ", ".join(results)
