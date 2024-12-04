import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL')
LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')