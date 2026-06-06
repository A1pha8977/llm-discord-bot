import trafilatura

from services.tools.registry import tool_registry


@tool_registry.register(
    name="extract",
    description=(
        "Extract clean, readable text content from a webpage. "
        "Use after a search has found relevant URLs, to get the full "
        "article text rather than just snippets. "
        "On error returns text starting with 'Error:'."
    ),
    params={
        "url": "The full URL of the webpage to extract content from",
        "max_length": "Maximum characters to return (default 8000)",
    },
    enabled=False
)
def extract_tool(url: str, max_length: int = 8000) -> str:
    """Download a webpage and extract the main text content via trafilatura.

    On failure (fetch error, no content, or unexpected exception), returns
    a string starting with ``"Error:"``.

    Args:
        url: The full URL of the webpage to extract.
        max_length: Maximum number of characters in the returned text.

    Returns:
        Extracted plain text, truncated to ``max_length`` characters with
        a ``"... [truncated]"`` suffix when applicable.
    """
    raise NotImplementedError("extract_tool")
