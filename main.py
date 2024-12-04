import os
import sys
import discord
import logging
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
from bot.views import PaymentView
from database.manager import DatabaseManager
from bot.commands import setup_commands
from bot.events import setup_events

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize database
db_manager = DatabaseManager(DB_URL)

# Pass the db_manager instance to other modules if necessary
# For example, you might need to modify how DatabaseManager is accessed in other files

# Setup commands and events
setup_commands(bot)
setup_events(bot)

if __name__ == "__main__":
    try:
        logging.info("Starting bot...")
        bot.run(TOKEN)
    except discord.LoginFailure:
        logging.error("Invalid token provided")
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        logging.info("Shutting down...")