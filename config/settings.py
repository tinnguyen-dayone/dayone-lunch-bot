import os
from dotenv import load_dotenv
from pathlib import Path

# Get the project root directory
root_dir = Path(__file__).parent.parent

# Check for .env.local first, then fall back to .env
env_local = root_dir / '.env.local'
env_default = root_dir / '.env'

if env_local.exists():
    load_dotenv(env_local)
    print("Loaded environment from .env.local")
else:
    load_dotenv(env_default)
    print("Loaded environment from .env")

TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
SENTRY_DSN = os.getenv('SENTRY_DSN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

DB_URL = os.getenv('DB_URL')

LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')

# Database pool settings
DB_MIN_CONNECTIONS = int(os.getenv('DB_MIN_CONNECTIONS', '1'))
DB_MAX_CONNECTIONS = int(os.getenv('DB_MAX_CONNECTIONS', '10'))