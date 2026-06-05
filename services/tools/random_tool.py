import random

from services.tools.registry import tool_registry


@tool_registry.register(
    "random",
    description="Generate one or more random numbers. Use for dice, random selection, draw lots, etc.",
    params={
        "count": "How many random numbers to generate (required)",
        "max_val": "Maximum value for each random number (default 6)",
    },
)
def random_tool(count: int, max_val: int = 6) -> str:
    if count < 1:
        return f"random_tool error: count must be >= 1, got {count}"
    if max_val < 1:
        return f"random_tool error: max_val must be >= 1, got {max_val}"
    results = [str(random.randint(1, max_val)) for _ in range(count)]
    return ", ".join(results)
