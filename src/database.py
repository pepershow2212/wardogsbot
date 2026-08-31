import aiosqlite
import os

DB_PATH = "data/posts.db"


async def init_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posted_tweets (
                tweet_id TEXT PRIMARY KEY,
                username TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def _ensure_table(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS posted_tweets (
            tweet_id TEXT PRIMARY KEY,
            username TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

async def is_posted(tweet_id: str) -> bool:
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        cursor = await db.execute(
            "SELECT 1 FROM posted_tweets WHERE tweet_id = ?", (tweet_id,)
        )
        return await cursor.fetchone() is not None


async def mark_posted(tweet_id: str, username: str):
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        await db.execute(
            "INSERT OR IGNORE INTO posted_tweets (tweet_id, username) VALUES (?, ?)",
            (tweet_id, username),
        )
        await db.commit()


async def get_stats() -> dict:
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        cursor = await db.execute("SELECT COUNT(*) FROM posted_tweets")
        row = await cursor.fetchone()
        return {"total_posted": row[0] if row else 0}
