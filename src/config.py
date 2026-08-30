import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", 30))
TWITTER_USERNAMES = [
    u.strip()
    for u in os.getenv("TWITTER_USERNAMES", "").split(",")
    if u.strip()
]
STEAM_APP_ID = os.getenv("STEAM_APP_ID", "1867240")
