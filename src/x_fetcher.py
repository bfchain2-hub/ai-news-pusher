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

    async def _search_tweets(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> List[dict]:
        """执行一次 search/recent 请求，返回 data 列表。"""
        url = f"{self.base_url}/2/tweets/search/recent"
        params = {
            "query": query,
            "max_results": "100",
            "tweet.fields": "created_at,public_metrics,lang,author_id",
        }
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("X search 失败 status=%s: %s", resp.status, text[:200])
                    return []
                data = await resp.json()
                return data.get("data") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("X search 请求异常: %s", exc)
            return []

    def _items_to_posts(self, items: List[dict]) -> List[XPost]:
        """将 API 返回的 item 列表转为 XPost 列表，并过滤 24 小时内。"""
        posts: List[XPost] = []
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

        return posts

    async def fetch_top_ai_posts(
        self,
        max_items: int = 25,
        influencer_handles: List[str] | None = None,
    ) -> List[Article]:
        """抓取最近24小时内 AI 相关高热度帖子；若配置了 AI 圈大佬账号，会同时抓取其推文并按点赞/转发/评论排序。"""
        if not self.bearer_token:
            return []

        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)
        seen_ids: set[str] = set()
        all_posts: List[XPost] = []

        # 1) 通用 AI 关键词搜索
        query_main = '("人工智能" OR AI OR "大模型" OR "生成式AI" OR "LLM" OR "GPT") -is:retweet'
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            items_main = await self._search_tweets(session, query_main)
            for p in self._items_to_posts(items_main):
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    all_posts.append(p)

            # 2) 可选：AI 大佬账号近期推文（带 AI 关键词以控制数量）
            if influencer_handles:
                # 每个 handle 只取字母数字下划线，避免注入
                safe = [h.strip() for h in influencer_handles if h and h.strip().replace("_", "").isalnum()]
                if safe:
                    from_part = " OR ".join(f"from:{h}" for h in safe[:10])  # 最多 10 个，避免 query 过长
                    query_influencers = f"({from_part}) (AI OR 大模型 OR 人工智能 OR GPT OR LLM) -is:retweet"
                    items_infl = await self._search_tweets(session, query_influencers)
                    for p in self._items_to_posts(items_infl):
                        if p.id not in seen_ids:
                            seen_ids.add(p.id)
                            all_posts.append(p)

        if not all_posts:
            logger.info("未从 X 获取到符合条件的帖子")
            return []

        def score(p: XPost) -> float:
            return p.like_count + p.retweet_count * 2 + p.quote_count * 1.5 + p.reply_count * 0.5

        all_posts.sort(key=score, reverse=True)
        top_posts = all_posts[:max_items]

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

        logger.info("成功从 X 获取并转换 %d 条热门帖子（含大佬账号）", len(articles))
        return articles


__all__ = ["XFetcher"]

