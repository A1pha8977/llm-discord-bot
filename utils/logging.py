import logging
import logging.handlers
import os


def setup(level: int = logging.INFO):
    root = logging.getLogger()
    if root.handlers:
        return

    os.makedirs("logs", exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        "logs/bot.log",
        when="midnight",
        encoding="utf-8",
        backupCount=30,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
