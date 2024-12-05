import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_URL = os.getenv('DB_URL') 

# Ensure DB_URL has proper SSL mode and uses TCP/IP
if DB_URL and 'sslmode=' not in DB_URL:
    DB_URL = f"{DB_URL}{'?' if '?' not in DB_URL else '&'}sslmode=require"

LUNCH_PRICE = os.getenv('LUNCH_PRICE', '55.000 VND')