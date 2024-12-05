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
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')

# Log the loaded environment variables for debugging
logging.info(f"Loaded DISCORD_TOKEN: {'***' if TOKEN else 'Not Set'}")
logging.info(f"Loaded DB_URL: {DB_URL}")
logging.info(f"Loaded LUNCH_PRICE: {LUNCH_PRICE}")

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize database
try:
    db_manager = DatabaseManager(DB_URL)
except Exception as e:
    logging.error(f"Database connection error: {e}")
    sys.exit(1)

# Pass the db_manager instance to other modules if necessary
# For example, you might need to modify how DatabaseManager is accessed in other files

# Prevent multiple setups
if not getattr(bot, 'commands_setup', False):
    setup_commands(bot)
    bot.commands_setup = True
if not getattr(bot, 'events_setup', False):
    setup_events(bot)
    bot.events_setup = True

# Remove or comment out the following event handlers if they're only related to PostgreSQL
# @bot.event
# async def on_disconnect():
#     logging.info("Bot has disconnected.")

# @bot.event
# async def on_resume():
#     logging.info("Bot has resumed connection.")

@bot.event
async def on_shutdown():
    logging.info("Shutting down the bot...")
    db_manager.close()

if __name__ == "__main__":
    async def main():
        try:
            logging.info("Starting bot...")
            await bot.start(TOKEN)
        except discord.LoginFailure:
            logging.error("Invalid token provided")
        except Exception as e:
            logging.error(f"Error: {e}")
        finally:
            await on_shutdown()
            logging.info("Bot has been shut down.")
    
    asyncio.run(main())