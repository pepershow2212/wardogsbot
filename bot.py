import discord
from discord.ext import commands, tasks
from discord import ui, app_commands
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import config
from twitter_scraper import fetch_tweets, Tweet
from steam_scraper import fetch_steam_news, SteamPost
from translator import translate_to_russian
from database import init_db, is_posted, mark_posted, get_stats

TOKENS = config.BOT_TOKENS
NEWS_TOKEN = config.DISCORD_TOKEN

intents_default = discord.Intents.default()
intents_news = discord.Intents.default()
intents_news.message_content = True

# === Helpers V2 (русский) ===

def build_steam_container(post: SteamPost, translated: str) -> ui.LayoutView:
    parts = translated.split("\n\n", 1)
    ru_title = parts[0] if parts else post.title
    ru_content = parts[1] if len(parts) > 1 else translated
    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=discord.Color.dark_blue())
    container.add_item(ui.TextDisplay(f"## WARDOGS Steam"))
    container.add_item(ui.TextDisplay(f"**{ru_title[:256]}**"))
    if ru_content:
        container.add_item(ui.TextDisplay(ru_content[:3500]))
    if post.image_url:
        try:
            from discord import MediaGalleryItem
            container.add_item(ui.MediaGallery(MediaGalleryItem(media=post.image_url)))
        except Exception:
            pass
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
    container.add_item(
        ui.Section(
            ui.TextDisplay(f"-# Steam • <t:{post.timestamp}:D>" if str(post.timestamp).isdigit() else f"-# Steam • {post.timestamp}"),
            accessory=ui.Button(label="Открыть в Steam", url=post.link if post.link.startswith("http") else "https://store.steampowered.com/app/1867240/", emoji="🔗"),
        )
    )
    view.add_item(container)
    return view


def build_tweet_container(tweet: Tweet, translated: str) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=discord.Color.gold())
    container.add_item(ui.TextDisplay(f"## @{tweet.username}"))
    container.add_item(ui.TextDisplay(translated[:3800] or "Нет текста"))
    if tweet.image_url:
        try:
            from discord import MediaGalleryItem
            container.add_item(ui.MediaGallery(MediaGalleryItem(media=tweet.image_url)))
        except Exception:
            pass
    container.add_item(ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
    container.add_item(
        ui.Section(
            ui.TextDisplay(f"-# X (Twitter) • {tweet.timestamp}"),
            accessory=ui.Button(label="Открыть пост", url=tweet.link if tweet.link.startswith("http") else f"https://x.com/{tweet.username}", emoji="💬"),
        )
    )
    view.add_item(container)
    return view


def create_bot(token: str, index: int):
    bot = commands.Bot(command_prefix="!", intents=intents_default)

    @bot.event
    async def on_ready():
        print(f"[Bot {index + 1}] Logged in as {bot.user}")
        activity = discord.Game(name="🛠️Разработка...")
        await bot.change_presence(status=discord.Status.dnd, activity=activity)

    return bot


def create_news_bot(token: str):
    bot = commands.Bot(command_prefix="!", intents=intents_news)

    @tasks.loop(minutes=config.CHECK_INTERVAL_MINUTES)
    async def check_tweets():
        channel = bot.get_channel(config.CHANNEL_ID)
        if not channel:
            return
        for username in config.TWITTER_USERNAMES:
            tweets = await fetch_tweets(username)
            for tweet in tweets:
                if await is_posted(tweet.id):
                    continue
                translated = await asyncio.to_thread(translate_to_russian, tweet.text)
                view = build_tweet_container(tweet, translated)
                await channel.send(view=view)
                await mark_posted(tweet.id, username)

    @tasks.loop(minutes=config.CHECK_INTERVAL_MINUTES)
    async def check_steam():
        channel = bot.get_channel(config.CHANNEL_ID)
        if not channel:
            return
        posts = await fetch_steam_news(config.STEAM_APP_ID)
        for post in posts:
            if await is_posted(f"steam_{post.id}"):
                continue
            full_text = f"{post.title}\n\n{post.content}"
            translated = await asyncio.to_thread(translate_to_russian, full_text)
            view = build_steam_container(post, translated)
            await channel.send(view=view)
            await mark_posted(f"steam_{post.id}", "steam")

    @check_tweets.before_loop
    async def before_check():
        await bot.wait_until_ready()

    @check_steam.before_loop
    async def before_check_steam():
        await bot.wait_until_ready()

    class HelpSelect(ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label="/testpost", description="Тестовый пост"),
                discord.SelectOption(label="/post", description="Проверка новых постов"),
                discord.SelectOption(label="/stats", description="Статистика бота"),
                discord.SelectOption(label="/users", description="Отслеживаемые аккаунты"),
            ]
            super().__init__(placeholder="Выбери команду...", options=options)

        async def callback(self, interaction: discord.Interaction):
            descs = {
                "/testpost": "Показывает тестовые посты (Twitter + Steam).",
                "/post": "Принудительная проверка новых твитов и Steam новостей.",
                "/stats": "Показывает статистику отправленных постов.",
                "/users": "Список отслеживаемых Twitter аккаунтов и Steam.",
            }
            embed = discord.Embed(title=f"`{self.values[0]}`", description=descs.get(self.values[0], "Неизвестная команда"), color=discord.Color.blue())
            await interaction.response.edit_message(embed=embed, view=self.view)

    class HelpView(ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.add_item(HelpSelect())

    @bot.event
    async def on_ready():
        await init_db()
        await bot.change_presence(status=discord.Status.dnd, activity=discord.CustomActivity(name="Слежу за новостями"))
        try:
            synced = await bot.tree.sync()
            print(f"[News] Synced {len(synced)} commands as {bot.user}")
        except Exception as e:
            print(f"[News] Sync error: {e}")
        if not check_tweets.is_running():
            check_tweets.start()
        if not check_steam.is_running():
            check_steam.start()
        print(f"[News] Logged in as {bot.user} | Twitter: {config.TWITTER_USERNAMES} | Steam: {config.STEAM_APP_ID}")

    @bot.tree.command(name="testpost", description="Тестовый пост V2 (только на русском)")
    @app_commands.default_permissions(administrator=True)
    async def testpost(interaction: discord.Interaction):
        demo_post = SteamPost(id="demo", title="WARDOGS Update v2.1", content="Major update with new maps, weapons, and game modes.", link="https://store.steampowered.com/app/1867240/", timestamp="1725000000")
        translated = "Обновление WARDOGS v2.1\n\nКрупное обновление с новыми картами, оружием и игровыми режимами. Исправлены баги и улучшена производительность."
        view = build_steam_container(demo_post, translated)
        await interaction.response.send_message(view=view)
        demo_tweet = Tweet(id="demo2", username="wardogs", text="Just pushed a huge update!", link="https://x.com/wardogs", timestamp="2026-08-30")
        translated2 = "Только что выпустил огромное обновление! Новые функции, исправления ошибок и улучшения производительности. Попробуйте!"
        view2 = build_tweet_container(demo_tweet, translated2)
        await interaction.followup.send(view=view2)

    @bot.tree.command(name="post", description="Проверить новые посты вручную")
    @app_commands.default_permissions(administrator=True)
    async def manual_post(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        count = 0
        try:
            for username in config.TWITTER_USERNAMES:
                try:
                    tweets = await fetch_tweets(username)
                except Exception as e:
                    print(f"[post] fetch {username} error: {e}")
                    continue
                for tweet in tweets:
                    if await is_posted(tweet.id):
                        continue
                    try:
                        translated = await asyncio.to_thread(translate_to_russian, tweet.text)
                    except Exception:
                        translated = tweet.text
                    view = build_tweet_container(tweet, translated)
                    await interaction.followup.send(view=view)
                    await mark_posted(tweet.id, username)
                    count += 1
            try:
                posts = await fetch_steam_news(config.STEAM_APP_ID)
            except Exception as e:
                print(f"[post] steam fetch error: {e}")
                posts = []
            for post in posts:
                if await is_posted(f"steam_{post.id}"):
                    continue
                full_text = f"{post.title}\n\n{post.content}"
                try:
                    translated = await asyncio.to_thread(translate_to_russian, full_text)
                except Exception:
                    translated = full_text[:1024]
                view = build_steam_container(post, translated)
                await interaction.followup.send(view=view)
                await mark_posted(f"steam_{post.id}", "steam")
                count += 1
            if count == 0:
                await interaction.followup.send("Новых постов не найдено. Twitter/Steam пока без обновлений.")
            else:
                await interaction.followup.send(f"Готово! Отправлено {count} постов.")
        except Exception as e:
            print(f"[post] error: {e}")
            try:
                await interaction.followup.send(f"Ошибка: {e}")
            except Exception:
                pass

    @bot.tree.command(name="stats", description="Статистика бота")
    @app_commands.default_permissions(administrator=True)
    async def stats(interaction: discord.Interaction):
        data = await get_stats()
        embed = discord.Embed(title="📊 Bot Statistics", color=discord.Color.blue())
        embed.add_field(name="Total Posts Sent", value=str(data["total_posted"]))
        embed.add_field(name="Tracked Twitter Users", value=str(len(config.TWITTER_USERNAMES)))
        embed.add_field(name="Steam App ID", value=config.STEAM_APP_ID)
        embed.add_field(name="Check Interval", value=f"Every {config.CHECK_INTERVAL_MINUTES} min")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="users", description="Отслеживаемые аккаунты")
    @app_commands.default_permissions(administrator=True)
    async def users(interaction: discord.Interaction):
        embed = discord.Embed(title="👥 Tracked Accounts", color=discord.Color.purple())
        for i, u in enumerate(config.TWITTER_USERNAMES, 1):
            embed.add_field(name=f"Twitter {i}.", value=f"`@{u}`", inline=True)
        embed.add_field(name="🎮 Steam", value=f"App ID: `{config.STEAM_APP_ID}`", inline=False)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="commands", description="Список всех команд")
    async def commands_list(interaction: discord.Interaction):
        embed = discord.Embed(title="📖 Commands", description="Выбери команду из меню ниже.", color=discord.Color.teal())
        await interaction.response.send_message(embed=embed, view=HelpView())

    return bot


async def main():
    bots = [create_bot(t, i) for i, t in enumerate(TOKENS)]
    news_bot = create_news_bot(NEWS_TOKEN)
    all_bots = bots + [news_bot]
    await asyncio.gather(*(b.start(t) for b, t in zip(all_bots, TOKENS + [NEWS_TOKEN])))

if __name__ == "__main__":
    asyncio.run(main())
