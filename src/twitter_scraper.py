import aiohttp
import re
import asyncio
from dataclasses import dataclass
from config import TWITTER_BEARER_TOKEN


X_API_BASE = "https://api.x.com/2"

# Расширенный список — xcancel + живые nitter форки
NITTER_INSTANCES = [
    "https://xcancel.com",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.tiekoetter.com",
    "https://nitter.kavin.rocks",
    "https://nitter.projectsegfau.lt",
    "https://nitter.moomoo.me",
    "https://nitter.etherred.net",
    "https://n.cyy.sh",
    "https://nuku.trabun.org",
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
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                print(f"[Twitter] User lookup {username} failed: {resp.status}")
                return None
            data = await resp.json()
            user_id = data["data"]["id"]
            _user_id_cache[username] = user_id
            print(f"[Twitter] Resolved @{username} -> ID {user_id}")
            return user_id
    except Exception as e:
        print(f"[Twitter] User lookup {username} error: {e}")
        return None


async def fetch_tweets(username: str) -> list[Tweet]:
    # 1. Пробуем X API если токен есть и не 402
    if TWITTER_BEARER_TOKEN:
        try:
            async with aiohttp.ClientSession() as session:
                user_id = await _get_user_id(session, username)
                if user_id:
                    url = f"{X_API_BASE}/users/{user_id}/tweets"
                    params = {
                        "max_results": 10,
                        "tweet.fields": "created_at,attachments",
                        "expansions": "attachments.media_keys",
                        "media.fields": "url,type",
                    }
                    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
                    async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        body = await resp.text()
                        print(f"[Twitter] GET {url} -> {resp.status}")
                        if resp.status == 200:
                            data = await resp.json()
                            count = len(data.get("data", []))
                            print(f"[Twitter] Got {count} tweets for @{username} via API")
                            if count:
                                return _parse_api_response(data, username)
                        elif resp.status == 402:
                            print(f"[Twitter] API 402 Payment Required -> fallback")
                        else:
                            print(f"[Twitter] API response: {body[:500]}")
        except Exception as e:
            print(f"[Twitter] API error: {e}")

    # 2. Fallback: RSS (xcancel/nitter)
    rss_result = await _fetch_tweets_rss(username)
    if rss_result:
        return rss_result

    # 3. Последний шанс: syndication (публичный, без токена)
    try:
        synd = await _fetch_tweets_syndication(username)
        if synd:
            return synd
    except Exception as e:
        print(f"[Twitter] Syndication error: {e}")

    print(f"[Twitter] All sources failed for @{username}")
    return []


async def _fetch_tweets_rss(username: str) -> list[Tweet]:
    import feedparser

    async def _fetch_one(instance: str) -> list[Tweet] | None:
        url = f"{instance}/{username}/rss"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                ) as resp:
                    if resp.status == 429:
                        print(f"[Twitter] {instance} 429")
                        return None
                    if resp.status != 200:
                        return None
                    data = await resp.text()
                    if "whitelist" in data.lower() and "rss reader" in data.lower():
                        print(f"[Twitter] {instance} whitelist")
                        return None
                    tweets = _parse_nitter_feed(data, username)
                    tweets = [t for t in tweets if "whitelist" not in t.text.lower()]
                    if tweets:
                        print(f"[Twitter] RSS got {len(tweets)} tweets for @{username} from {instance}")
                        return tweets
        except Exception:
            return None
        return None

    # параллельно по 4 инстанса за раз, чтобы уложиться в 8с лимит Discord
    for i in range(0, len(NITTER_INSTANCES), 4):
        chunk = NITTER_INSTANCES[i:i+4]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[_fetch_one(inst) for inst in chunk]),
                timeout=6,
            )
            for r in results:
                if r:
                    return r
        except asyncio.TimeoutError:
            print(f"[Twitter] RSS chunk timeout")
            continue
    return []


async def _fetch_tweets_syndication(username: str) -> list[Tweet]:
    # Пробуем fxtwitter/vxtwitter API (публичный, без ключа)
    # https://api.fxtwitter.com/<username>/status/<id> требует id, но есть timeline через nitter уже
    # Используем syndication timeline json
    url = f"https://cdn.syndication.twimg.com/widgets/timelines/1684316625?domain=x.com&lang=en&suppress_response_codes=true"
    # Этот эндпоинт нестабилен, поэтому просто пробуем и не падаем
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
            id=tweet_id, username=username, text=text,
            link=link, timestamp=created_at, image_url=image_url,
        ))
    return tweets


def _parse_nitter_feed(data: str, username: str) -> list[Tweet]:
    import feedparser
    feed = feedparser.parse(data)
    tweets = []
    for entry in feed.entries[:10]:
        tweet_id = entry.get("id", "").split("/")[-1] or entry.get("link", "")
        # нормализуем id (только цифры)
        tweet_id = re.sub(r"\D", "", tweet_id) or tweet_id
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
        # иногда ссылка в nitter виде https://nitter.net/... -> меняем на x.com
        link = entry.get("link", "")
        if "nitter" in link or "xcancel" in link:
            # достаём id и собираем x.com ссылку
            if tweet_id:
                link = f"https://x.com/{username}/status/{tweet_id}"
        elif not link.startswith("http"):
            link = f"https://x.com/{username}/status/{tweet_id}"
        text = _clean_html(raw)
        if not text:
            continue
        tweets.append(Tweet(
            id=tweet_id, username=username, text=text,
            link=link, timestamp=entry.get("published", ""), image_url=image_url,
        ))
    return tweets


def _clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<a\s+href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
