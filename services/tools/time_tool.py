import time

from services.tools.registry import tool_registry


@tool_registry.register(
    name="time",
    tool_description=(
        "Get the current date and time. "
        "Call this BEFORE answering any time-sensitive question — "
        "you have no inherent knowledge of the current date. "
        "Returns a full date-time string like "
        "\"Thu Jun 5 14:30:00 2026 CST (UTC+0800)\" "
        "including weekday, month, day, HH:MM:SS, year, timezone "
        "abbreviation, and UTC offset. "
        "Always call this tool when the user mentions relative time "
        "(\"yesterday\", \"last week\", \"next month\", \"this year\") or asks "
        "\"what day is it\", \"what's the date\", or similar. "
        "Also call it before searching the web for time-sensitive "
        "information (e.g. \"yesterday's weather\" — you need today's "
        "date first to compute what \"yesterday\" means)."
    ),
    params={},
)
def get_time() -> str:
    return time.strftime("%c %Z (UTC%z)")
