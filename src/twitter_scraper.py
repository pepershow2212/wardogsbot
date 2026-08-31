import aiohttp
from dataclasses import dataclass
from config import TWITTER_BEARER_TOKEN


X_API_BASE = "https://api.x.com/2"


@dataclass
class Tweet:
    id: str
    username: str
    text: str
    link: str
    timestamp: str
    image_url: str = ""


_user_id_cache: dict[str, str] = {}


async def _get_user_id(session: aiohttp.ClientSession, username: str) -> str | None:
    if username in _user_id_cache:
        return _user_id_cache[username]
    url = f"{X_API_BASE}/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"[Twitter] User lookup {username} failed: {resp.status}")
                return None
            data = await resp.json()
            user_id = data["data"]["id"]
            _user_id_cache[username] = user_id
            return user_id
    except Exception as e:
        print(f"[Twitter] User lookup {username} error: {e}")
        return None


async def fetch_tweets(username: str) -> list[Tweet]:
    if not TWITTER_BEARER_TOKEN:
        print("[Twitter] TWITTER_BEARER_TOKEN not set, skipping")
        return []

    async with aiohttp.ClientSession() as session:
        user_id = await _get_user_id(session, username)
        if not user_id:
            return []

        url = f"{X_API_BASE}/users/{user_id}/tweets"
        params = {
            "max_results": 10,
            "tweet.fields": "created_at,attachments",
            "expansions": "attachments.media_keys",
            "media.fields": "url,type",
        }
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}

        try:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[Twitter] Fetch tweets for {username} failed: {resp.status} — {body[:200]}")
                    return []
                data = await resp.json()
        except Exception as e:
            print(f"[Twitter] Fetch tweets for {username} error: {e}")
            return []

    return _parse_response(data, username)


def _parse_response(data: dict, username: str) -> list[Tweet]:
    tweets_data = data.get("data", [])
    includes = data.get("includes", {})
    media_list = includes.get("media", [])

    media_map = {}
    for m in media_list:
        if m.get("type") == "photo" and m.get("url"):
            media_map[m["media_key"]] = m["url"]

    tweets = []
    for t in tweets_data:
        tweet_id = t["id"]
        text = t.get("text", "")
        created_at = t.get("created_at", "")
        link = f"https://x.com/{username}/status/{tweet_id}"

        image_url = ""
        attachments = t.get("attachments", {})
        for mk in attachments.get("media_keys", []):
            if mk in media_map:
                image_url = media_map[mk]
                break

        tweets.append(Tweet(
            id=tweet_id,
            username=username,
            text=text,
            link=link,
            timestamp=created_at,
            image_url=image_url,
        ))

    return tweets
