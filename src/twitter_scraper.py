import aiohttp
import feedparser
from dataclasses import dataclass


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


async def fetch_tweets(username: str) -> list[Tweet]:
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{username}/rss"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.text()
                    return _parse_feed(data, username)
        except Exception:
            continue
    return []


def _parse_feed(data: str, username: str) -> list[Tweet]:
    import re
    feed = feedparser.parse(data)
    tweets = []
    for entry in feed.entries[:10]:
        tweet_id = entry.get("id", "").split("/")[-1] or entry.get("link", "")
        raw = entry.get("summary", entry.get("title", ""))
        image_url = ""
        # ищем картинку в html
        m = re.search(r'<img[^>]+src="([^"]+)"', raw)
        if m:
            image_url = m.group(1)
        # иногда media_content
        if not image_url and "media_content" in entry:
            try:
                image_url = entry.media_content[0].get("url", "")
            except Exception:
                pass
        text = _clean_html(raw)
        tweets.append(
            Tweet(
                id=tweet_id,
                username=username,
                text=text,
                link=entry.get("link", ""),
                timestamp=entry.get("published", ""),
                image_url=image_url,
            )
        )
    return tweets


def _clean_html(text: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<a\s+href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
