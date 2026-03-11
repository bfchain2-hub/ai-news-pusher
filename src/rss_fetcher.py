import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiohttp
import feedparser


logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    summary: str
    link: str
    published: Optional[datetime]
    source_name: str
    category: str


class RSSFetcher:
    """异步RSS抓取器，负责从多个源并发抓取最近24小时的文章。"""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    async def _fetch_single(self, session: aiohttp.ClientSession, source: dict) -> List[Article]:
        url = source["url"]
        name = source.get("name", "Unknown")
        category = source.get("category", "未分类")
        articles: List[Article] = []

        try:
            async with session.get(url, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning("获取RSS失败: %s (%s), 状态码: %s", name, url, resp.status)
                    return []
                content = await resp.read()
        except asyncio.TimeoutError:
            logger.error("获取RSS超时: %s (%s)", name, url)
            return []
        except aiohttp.ClientError as exc:
            logger.error("获取RSS网络错误: %s (%s) - %s", name, url, exc)
            return []

        try:
            parsed = await asyncio.to_thread(feedparser.parse, content)
        except Exception as exc:  # noqa: BLE001
            logger.error("解析RSS失败: %s (%s) - %s", name, url, exc)
            return []

        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=1)

        for entry in parsed.entries:
            published_dt = self._extract_published(entry)
            if published_dt is not None and published_dt < threshold:
                continue

            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "").strip() or getattr(entry, "description", "").strip()
            link = getattr(entry, "link", "").strip()

            if not title or not link:
                continue

            articles.append(
                Article(
                    title=title,
                    summary=summary,
                    link=link,
                    published=published_dt,
                    source_name=name,
                    category=category,
                )
            )

        logger.info("RSS源 %s 获取到 %d 条候选文章", name, len(articles))
        return articles

    @staticmethod
    def _extract_published(entry) -> Optional[datetime]:
        """从entry中提取发布时间，尽量使用UTC时间。"""
        struct_time = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if struct_time is None:
            return None
        try:
            # struct_time.tm_gmtoff在部分实现中存在；没有时按UTC处理
            dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            return None
        return dt

    async def fetch_all(self, sources: List[dict]) -> List[Article]:
        """从所有RSS源并发抓取最近24小时的文章。"""
        if not sources:
            logger.warning("RSS源列表为空")
            return []

        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [self._fetch_single(session, src) for src in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        articles: List[Article] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("抓取RSS源时发生未捕获异常: %s", result)
                continue
            articles.extend(result)

        # 按发布时间倒序排序（最新在前），无发布时间的排在最后
        articles.sort(key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        logger.info("总计从所有RSS源获取到 %d 条文章（24小时内）", len(articles))
        return articles


__all__ = ["Article", "RSSFetcher"]

