import aiohttp
import re
from dataclasses import dataclass
from config import TWITTER_BEARER_TOKEN


X_API_BASE = "https://api.x.com/2"

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
]


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
            print(f"[Twitter] Resolved @{username} → ID {user_id}")
            return user_id
    except Exception as e:
        print(f"[Twitter] User lookup {username} error: {e}")
        return None


async def fetch_tweets(username: str) -> list[Tweet]:
    if not TWITTER_BEARER_TOKEN:
        print("[Twitter] TWITTER_BEARER_TOKEN not set, trying Nitter fallback")
        return await _fetch_tweets_nitter(username)

    async with aiohttp.ClientSession() as session:
        user_id = await _get_user_id(session, username)
        if not user_id:
            return await _fetch_tweets_nitter(username)

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
                body = await resp.text()
                print(f"[Twitter] GET {url} → {resp.status}")
                if resp.status != 200:
                    print(f"[Twitter] API response: {body[:500]}")
                    print(f"[Twitter] API unavailable, trying Nitter fallback")
                    return await _fetch_tweets_nitter(username)
                data = await resp.json()
                count = len(data.get("data", []))
                print(f"[Twitter] Got {count} tweets for @{username}")
        except Exception as e:
            print(f"[Twitter] API error: {e}, trying Nitter fallback")
            return await _fetch_tweets_nitter(username)

    return _parse_api_response(data, username)


async def _fetch_tweets_nitter(username: str) -> list[Tweet]:
    import feedparser
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{username}/rss"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.text()
                    tweets = _parse_nitter_feed(data, username)
                    if tweets:
                        print(f"[Twitter] Nitter fallback got {len(tweets)} tweets for @{username} from {instance}")
                        return tweets
        except Exception:
            continue
    print(f"[Twitter] All sources failed for @{username}")
    return []


def _parse_api_response(data: dict, username: str) -> list[Tweet]:
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


def _parse_nitter_feed(data: str, username: str) -> list[Tweet]:
    import feedparser
    feed = feedparser.parse(data)
    tweets = []
    for entry in feed.entries[:10]:
        tweet_id = entry.get("id", "").split("/")[-1] or entry.get("link", "")
        raw = entry.get("summary", entry.get("title", ""))
        image_url = ""
        m = re.search(r'<img[^>]+src="([^"]+)"', raw)
        if m:
            image_url = m.group(1)
        if not image_url and "media_content" in entry:
            try:
                image_url = entry.media_content[0].get("url", "")
            except Exception:
                pass
        text = _clean_html(raw)
        tweets.append(Tweet(
            id=tweet_id,
            username=username,
            text=text,
            link=entry.get("link", ""),
            timestamp=entry.get("published", ""),
            image_url=image_url,
        ))
    return tweets


def _clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<a\s+href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
