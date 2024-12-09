import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
SENTRY_DSN = os.getenv('SENTRY_DSN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# Always set SSL mode to disable for local Docker network
if DB_URL:
    if '?' in DB_URL:
        DB_URL = DB_URL.split('?')[0]
    DB_URL = f"{DB_URL}?sslmode=disable"

LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')