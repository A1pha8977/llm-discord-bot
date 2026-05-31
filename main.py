import os
import dotenv

from utils.logging import setup as setup_logging
import my_bot

def main():
    dotenv.load_dotenv()
    setup_logging()
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN is not set")
    bot = my_bot.BOT
    bot.run(token=DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()