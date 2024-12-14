from config.settings import *
import os

print("\nEnvironment Configuration:")
print("-" * 50)
print(f"Current ENV file: {'.env.local' if (Path(__file__).parent.parent / '.env.local').exists() else '.env'}")
print(f"ENVIRONMENT: {ENVIRONMENT}")
print(f"DB_URL: {DB_URL}")
print(f"DISCORD_TOKEN: {'***' if TOKEN else 'Not Set'}")
print(f"LUNCH_PRICE: {LUNCH_PRICE}")
print(f"DB_MIN_CONNECTIONS: {DB_MIN_CONNECTIONS}")
print(f"DB_MAX_CONNECTIONS: {DB_MAX_CONNECTIONS}")
print("-" * 50)
