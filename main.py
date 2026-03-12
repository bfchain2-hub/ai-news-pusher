import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from src.content_summarizer import ContentSummarizer
from src.rss_fetcher import RSSFetcher
from src.x_fetcher import XFetcher
from src.wechat_pusher import WechatPusher


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CACHE_DIR = BASE_DIR / "cache"
CACHE_FILE = CACHE_DIR / "last_articles.json"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def load_config() -> List[Dict[str, Any]]:
    rss_config_path = CONFIG_DIR / "rss_sources.json"
    if not rss_config_path.exists():
        raise FileNotFoundError(f"RSS配置文件不存在: {rss_config_path}")

    with rss_config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("rss_sources.json 格式错误: 'sources' 必须是列表")

    return sources


def load_env() -> None:
    # 允许在本地使用 .env，GitHub Actions 中则使用 Secrets 环境变量
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # 读取系统环境变量中已有配置


def load_cache() -> Dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_cache(data: Dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        # 缓存失败不影响主流程
        logging.getLogger(__name__).warning("写入缓存失败", exc_info=True)


async def run() -> None:
    setup_logging()
    logger = logging.getLogger("ai-news-pusher")

    load_env()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    server_chan_key = os.getenv("SERVER_CHAN_KEY")
    x_bearer_token = os.getenv("X_BEARER_TOKEN")

    if not openai_api_key:
        logger.error("环境变量 OPENAI_API_KEY 未配置")
        return
    if not server_chan_key:
        logger.error("环境变量 SERVER_CHAN_KEY 未配置")
        return

    try:
        sources = load_config()
    except Exception as exc:  # noqa: BLE001
        logger.error("加载RSS配置失败: %s", exc)
        return

    fetcher = RSSFetcher()
    summarizer = ContentSummarizer(api_key=openai_api_key, base_url=openai_base_url)
    pusher = WechatPusher(send_key=server_chan_key)
    x_fetcher: XFetcher | None = None
    if x_bearer_token:
        x_fetcher = XFetcher(bearer_token=x_bearer_token)

    logger.info("开始抓取RSS资讯...")
    articles = await fetcher.fetch_all(sources)

    if x_fetcher is not None:
        logger.info("检测到 X_BEARER_TOKEN，开始抓取 X 热门帖子...")
        x_articles = await x_fetcher.fetch_top_ai_posts(max_items=20)
        articles.extend(x_articles)

    if not articles:
        logger.warning("未从RSS源和 X 中获取到任何文章，将仍然推送一条提示消息。")
        await pusher.push([])
        return

    # 简单缓存机制：如果标题+链接集合与上次相同，则直接跳过总结，避免重复消耗
    cache = load_cache()
    current_signature = sorted({f"{a.title}::{a.link}" for a in articles})
    last_signature = cache.get("signature")

    if current_signature == last_signature:
        logger.info("与上次抓取结果相同，跳过GPT总结步骤，直接推送缓存结果。")
        cached_items = cache.get("summaries") or []
        await pusher.push(cached_items)
        return

    logger.info("开始调用GPT生成新闻摘要...")
    summaries = await summarizer.summarize(articles, max_items=15)

    if not summaries:
        logger.warning("GPT未返回有效摘要，将推送原始标题列表。")
        fallback_items = [
            {
                "title": a.title,
                "summary": a.summary[:80],
                "link": a.link,
                "source": a.source_name,
                "category": a.category,
            }
            for a in articles[:15]
        ]
        await pusher.push(fallback_items)
        return

    logger.info("开始推送到微信（Server酱）...")
    ok = await pusher.push(summaries)

    if ok:
        save_cache({"signature": current_signature, "summaries": summaries})
        logger.info("任务完成，缓存已更新。")
    else:
        logger.error("任务完成但推送失败，缓存不更新。")


if __name__ == "__main__":
    asyncio.run(run())

