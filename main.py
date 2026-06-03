import os
import dotenv

from utils.logging import setup as setup_logging
from utils import config
import my_bot

def main():
    dotenv.load_dotenv()
    setup_logging()
    config.validate_all()
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not DISCORD_BOT_TOKEN:
        raise ValueError("Missing required environment variable: DISCORD_BOT_TOKEN")
    bot = my_bot.BOT
    bot.run(token=DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()