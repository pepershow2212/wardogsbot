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
# 4 основных бота через env: BOT_TOKENS=tok1,tok2,tok3,tok4 или BOT1_TOKEN, BOT2_TOKEN...
_raw = os.getenv("BOT_TOKENS", "")
if _raw:
    BOT_TOKENS = [t.strip() for t in _raw.split(",") if t.strip()]
else:
    BOT_TOKENS = [os.getenv(f"BOT{i}_TOKEN") for i in range(1, 5)]
    BOT_TOKENS = [t for t in BOT_TOKENS if t]
