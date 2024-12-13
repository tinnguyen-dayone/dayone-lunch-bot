import logging
import sys
import os
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Setup logging before Sentry initialization
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot.log')
    ]
)

# Configure Sentry SDK with advanced options
sentry_logging = LoggingIntegration(
    level=logging.INFO,        # Capture info and above as breadcrumbs
    event_level=logging.ERROR  # Send errors as events
)


sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment=os.getenv('ENVIRONMENT', 'development'),
    integrations=[
        sentry_logging
    ],
    # Configure additional context
    before_send=lambda event, hint: {
        **event,
        "tags": {
            **(event.get("tags", {})),
            "bot_version": "1.0.0",
        }
    }
)


# Create logger for the bot
bot_logger = logging.getLogger('bot')
bot_logger.setLevel(logging.INFO)

# Test log statements

import discord
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


# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')
DB_MIN_CONNECTIONS = int(os.getenv('DB_MIN_CONNECTIONS', 1))
DB_MAX_CONNECTIONS = int(os.getenv('DB_MAX_CONNECTIONS', 10))

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

# Enhance error tracking
@bot.event
async def on_error(event, *args, **kwargs):
    sentry_sdk.capture_exception()
    logging.error(f"Error in {event}: {sys.exc_info()}")

# Initialize database with connection pool settings
try:
    db_manager = DatabaseManager(
        DB_URL,
        min_conn=DB_MIN_CONNECTIONS,
        max_conn=DB_MAX_CONNECTIONS
    )
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
            sentry_sdk.capture_message("Invalid Discord token", level="error")
        except Exception as e:
            logging.error(f"Error: {e}")
            sentry_sdk.capture_exception()
        finally:
            await on_shutdown()
            logging.info("Bot has been shut down.")
    
    asyncio.run(main())