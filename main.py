"""Application entry point.

Values defined in ``.env`` and ``.yaml`` are loaded/validated before the
Discord bot is created and run.

Example:

.. code-block:: bash

    python main.py
"""

import os

from utils.logging import setup as setup_logging
from utils import config
from my_bot import create_bot


def main():
    """Load env vars, validate configs, and start the bot."""
    setup_logging()
    config.validate_all()
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not DISCORD_BOT_TOKEN:
        raise ValueError("Missing required environment variable: DISCORD_BOT_TOKEN")
    bot = create_bot()
    bot.run(token=DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
