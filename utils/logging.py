"""Logging setup with daily rotating file handler."""

import logging
import logging.handlers
import os
import sys


def setup(level: int = logging.INFO):
    """Configure root logger with file + console handlers.

    Creates the ``logs/`` directory relative to the project root.  Log files
    rotate at midnight and are kept for 30 days.  ``discord``, ``asyncio``,
    and ``httpx`` loggers are suppressed to ``WARNING`` to reduce noise.

    Console output is fixed at ``WARNING``; file output respects *level*.

    Args:
        level: File handler level (default ``logging.INFO``).
    """
    root = logging.getLogger()
    if root.handlers:
        return

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except PermissionError:
        print(f"ERROR: Cannot create log directory: {log_dir}", file=sys.stderr)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        root.setLevel(level)
        root.addHandler(handler)
        return

    handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        when="midnight",
        encoding="utf-8",
        backupCount=30,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root.setLevel(level)
    root.addHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root.addHandler(console)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
