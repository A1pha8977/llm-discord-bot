import os

from tavily import TavilyClient

from services.tools.registry import tool_registry


class TavilySearch:
    """Tavily web search client. Reads ``TAVILY_API_KEY`` from ``.env``."""

    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if api_key is None:
            raise ValueError("Missing TAVILY_API_KEY")
        self._client = TavilyClient(api_key=api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        time_range: str | None = None,
    ) -> str:
        """Execute a web search and return formatted plain-text results.

        Returns a string starting with ``"Search results for ..."``.
        On error, returns ``"Search parameter error: ..."`` or
        ``"Search API error: ..."``.
        """
        if max_results < 1 or max_results > 300:
            return (
                f"Search parameter error: max_results must be 1–300, got {max_results}"
            )

        if search_depth not in ("basic", "advanced"):
            return (
                f"Search parameter error: "
                f"search_depth must be 'basic' or 'advanced', "
                f"got '{search_depth}'"
            )

        if topic not in ("general", "news", "finance"):
            return (
                f"Search parameter error: "
                f"topic must be 'general', 'news', or 'finance', "
                f"got '{topic}'"
            )

        try:
            kwargs: dict = dict(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                topic=topic,
                include_answer="basic",
            )
            if time_range:
                kwargs["time_range"] = time_range

            result = self._client.search(**kwargs)

            lines = [f'Search results for "{query}":\n']
            answer = result.get("answer")
            if answer:
                lines.append(f"Summary: {answer}\n")

            for i, r in enumerate(result.get("results", []), 1):
                lines.append(f"{i}. {r['title']} — {r['url']}\n   {r['content']}")

            return "\n".join(lines)

        except Exception as e:
            return f"Search API error: {type(e).__name__}: {e}"


_tavily = TavilySearch()


@tool_registry.register(
    name="search",
    description=(
        "Search the web for real-time information. "
        "Use when you need current facts, recent events, or data beyond "
        "your knowledge cutoff. "
        "Returns formatted plain text: title, URL, and content snippet "
        "per result, plus an optional AI-generated summary. "
        "On error returns text starting with 'Search parameter error:' "
        "or 'Search API error:'."
    ),
    params={
        "query": "The search query string",
        "max_results": "Number of results (1–300, default 5)",
        "search_depth": (
            "Search depth: 'basic' (fast, default) or 'advanced' (thorough)"
        ),
        "topic": "Filter: 'general' (default), 'news', or 'finance'",
        "time_range": (
            "Time filter: 'day', 'week', 'month', 'year', or omit for any time"
        ),
    },
)
def web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str | None = None,
) -> str:
    """Search the web via Tavily and return plain-text results."""
    return _tavily.search(query, max_results, search_depth, topic, time_range)
