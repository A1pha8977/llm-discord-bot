from requests.models import Response


import re

import requests
import trafilatura

from services.tools.registry import tool_registry

# --- Constants ---
_HEAD_TIMEOUT = 10  # HEAD request timeout in seconds
_TEXT_MIME_TYPES: frozenset[str] = frozenset[str](
    {
        "text/html",
        "text/plain",
        "text/xml",
        "application/xhtml+xml",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
    }
)


def _is_http_url(url: str) -> bool:
    """Return True if *url* uses the http or https scheme."""
    return bool(re.match(r"^https?://", url, re.IGNORECASE))


def _get_content_type(url: str) -> str | None:
    """Probe *url* with a HEAD request and return its Content-Type.

    Returns:
        The stripped MIME type string (e.g. ``"text/html"``),
        or ``None`` if the HEAD request failed (caller should fall
        through to the full download path).
    """
    try:
        resp: Response = requests.head(
            url,
            timeout=_HEAD_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"},
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        # Strip parameters (e.g. "text/html; charset=utf-8")
        mime_type = content_type.split(";")[0].strip().lower()
        return mime_type
    except requests.RequestException:
        # HEAD request failed (405, timeout, etc.); return None and let the caller fall through
        return None


@tool_registry.register(
    name="extract",
    tool_description=(
        "Extract clean, readable text content from a text-based webpage "
        "(HTML, plain text, or XML only). "
        "IMPORTANT: Do NOT use on non-text URLs — images, videos, PDFs, "
        "file downloads, or binary content will be rejected. "
        "Use after a search has found relevant URLs, to get the full "
        "article text rather than just snippets. "
        "Returns the extracted plain text, or an error message starting "
        "with 'Error:' on failure."
    ),
    params={
        "url": "The full URL of a text-based webpage to extract content from",
        "max_length": {
            "description": "Maximum characters to return (default 8000)",
            "default": 8000,
            "minimum": 100,
            "maximum": 50000,
        },
    },
)
def extract_tool(url: str, max_length: int = 8000) -> str:
    """Download a text-based webpage and extract the main text content via trafilatura.

    Validates the URL scheme (http/https) and performs a HEAD request
    to reject non-text content types early, saving bandwidth and time.

    On failure returns a string starting with ``"Error:"``.

    Args:
        url: The full URL of the webpage to extract (http/https only, text-based).
        max_length: Maximum number of characters in the returned text.

    Returns:
        Extracted plain text, truncated when exceeding *max_length*.
    """
    if max_length < 100 or max_length > 50000:
        return f"Error: max_length must be 100–50000, got {max_length}"

    # 1. Validate URL scheme
    if not _is_http_url(url):
        return (
            f"Error: Unsupported URL scheme. Only http:// and https:// "
            f"URLs are allowed, got '{url[:80]}'"
        )

    # 2. HEAD probe Content-Type; reject non-text early
    content_type: str | None = _get_content_type(url)
    if content_type is not None and content_type not in _TEXT_MIME_TYPES:
        return (
            f"Error: URL points to non-text content "
            f"(Content-Type: '{content_type}'). This tool only works with "
            f"HTML, plain text, or XML pages."
        )

    # 3. Download and extract
    try:
        downloaded: str | None = trafilatura.fetch_url(url)
        if downloaded is None:
            return (
                f"Error: Could not fetch content from '{url}'. "
                f"The page may be inaccessible, blocked, or not a text-based webpage."
            )

        text: str | None = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
        )
        if not text:
            return (
                f"Error: No extractable text found at '{url}'. "
                f"The page may contain little text, be behind a paywall, "
                f"or consist mainly of non-text media."
            )

        if len(text) > max_length:
            text = text[:max_length].rstrip() + "\n... [truncated]"

        return text
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
