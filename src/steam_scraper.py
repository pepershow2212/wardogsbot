import aiohttp
from dataclasses import dataclass


STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid={app_id}&count=10&maxlength=1000&format=json"


@dataclass
class SteamPost:
    id: str
    title: str
    content: str
    link: str
    timestamp: str
    image_url: str = ""


async def fetch_steam_news(app_id: str) -> list[SteamPost]:
    url = STEAM_NEWS_URL.format(app_id=app_id)
    posts = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                items = data.get("appnews", {}).get("newsitems", [])
                for item in items[:10]:
                    # только официальные анонсы от разрабов
                    if item.get("feedname") != "steam_community_announcements":
                        continue
                    raw = item.get("contents", "")
                    image_url = ""
                    import re
                    m = re.search(r'<img[^>]+src="([^"]+)"', raw)
                    if m:
                        image_url = m.group(1)
                    posts.append(
                        SteamPost(
                            id=str(item.get("gid", "")),
                            title=item.get("title", ""),
                            content=_clean_html(raw),
                            link=item.get("url", ""),
                            timestamp=str(item.get("date", "")),
                            image_url=image_url,
                        )
                    )
    except Exception:
        pass
    return posts


def _clean_html(text: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    return text[:1024] if text else ""
