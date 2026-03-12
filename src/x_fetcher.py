import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiohttp

from .rss_fetcher import Article


logger = logging.getLogger(__name__)


@dataclass
class XPost:
    id: str
    text: str
    created_at: Optional[datetime]
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
    author_id: Optional[str]


class XFetcher:
    """从 X(Twitter) 获取 AI 相关高热度帖子，转换为 Article 供后续统一处理。

    说明：
    - 使用 Twitter API v2 /2/tweets/search/recent 接口
    - 需要 Bearer Token（在 GitHub Secrets 中通过 X_BEARER_TOKEN 提供）
    - 如无 Token，主流程会自动跳过本模块
    """

    def __init__(
        self,
        bearer_token: str,
        base_url: str = "https://api.twitter.com",
        timeout: int = 15,
    ) -> None:
        self.bearer_token = bearer_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_top_ai_posts(self, max_items: int = 20) -> List[Article]:
        """抓取最近24小时内 AI 相关的高热度帖子，并转换为 Article 列表。"""
        if not self.bearer_token:
            return []

        url = f"{self.base_url}/2/tweets/search/recent"
        # 关键词可以根据需要再调整
        query = '("人工智能" OR AI OR "大模型" OR "生成式AI") -is:retweet'
        params = {
            "query": query,
            "max_results": "100",  # 接口上限
            "tweet.fields": "created_at,public_metrics,lang,author_id",
        }

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error("获取 X 热帖失败，状态码=%s，响应=%s", resp.status, text)
                        return []
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("获取 X 热帖时发生异常: %s", exc)
            return []

        posts: List[XPost] = []
        items = data.get("data") or []
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=1)

        for item in items:
            try:
                created_at_str = item.get("created_at")
                created_at: Optional[datetime] = None
                if created_at_str:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at is not None and created_at < threshold:
                    continue

                metrics = item.get("public_metrics") or {}
                like_count = int(metrics.get("like_count", 0))
                retweet_count = int(metrics.get("retweet_count", 0))
                reply_count = int(metrics.get("reply_count", 0))
                quote_count = int(metrics.get("quote_count", 0))

                posts.append(
                    XPost(
                        id=str(item.get("id")),
                        text=str(item.get("text") or "").strip(),
                        created_at=created_at,
                        like_count=like_count,
                        retweet_count=retweet_count,
                        reply_count=reply_count,
                        quote_count=quote_count,
                        author_id=str(item.get("author_id") or "") or None,
                    )
                )
            except Exception:  # noqa: BLE001
                continue

        if not posts:
            logger.info("未从 X 获取到符合条件的帖子")
            return []

        def score(p: XPost) -> float:
            return p.like_count + p.retweet_count * 2 + p.quote_count * 1.5 + p.reply_count * 0.5

        posts.sort(key=score, reverse=True)
        top_posts = posts[:max_items]

        articles: List[Article] = []
        for p in top_posts:
            link = f"https://x.com/i/web/status/{p.id}"
            title = p.text.replace("\n", " ").strip()
            summary = f"X 热帖：👍{p.like_count} 🔁{p.retweet_count} 💬{p.reply_count}"
            articles.append(
                Article(
                    title=title,
                    summary=summary,
                    link=link,
                    published=p.created_at,
                    source_name="X 热门帖子",
                    category="社交媒体",
                )
            )

        logger.info("成功从 X 获取并转换 %d 条热门帖子", len(articles))
        return articles


__all__ = ["XFetcher"]

