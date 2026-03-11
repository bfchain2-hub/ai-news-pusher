import asyncio
import logging
from datetime import datetime
from typing import List

import aiohttp


logger = logging.getLogger(__name__)


class WechatPusher:
    """使用Server酱推送微信消息。"""

    def __init__(self, send_key: str, max_retries: int = 3) -> None:
        self.send_key = send_key
        self.max_retries = max_retries
        self.base_url = "https://sctapi.ftqq.com"

    def build_message(self, items: List[dict]) -> tuple[str, str]:
        """构建消息标题和内容（Markdown）。"""
        today = datetime.now().strftime("%Y-%m-%d")
        title = f"📰 AI日报 - {today}"

        if not items:
            desp = f"📰 AI日报 - {today}\n\n今天暂时没有抓取到新的AI相关资讯，欢迎明天再来查看。"
            return title, desp

        lines: List[str] = [f"📰 AI日报 - {today}", "", "🔥 今日热点"]

        for idx, item in enumerate(items, start=1):
            t = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            source = item.get("source", "")
            category = item.get("category", "")

            lines.append(f"{idx}. [{t}]({link})")
            if source or category:
                meta_parts = []
                if source:
                    meta_parts.append(f"来源：{source}")
                if category:
                    meta_parts.append(f"分类：{category}")
                lines.append("   " + " | ".join(meta_parts))
            if summary:
                lines.append(f"   {summary}")
            lines.append("")  # 空行分隔

        desp = "\n".join(lines).strip()
        return title, desp

    async def push(self, items: List[dict]) -> bool:
        """推送消息到Server酱，失败时自动重试。"""
        title, desp = self.build_message(items)
        url = f"{self.base_url}/{self.send_key}.send"

        payload = {
            "title": title,
            "desp": desp,
        }

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(1, self.max_retries + 1):
                try:
                    async with session.post(url, data=payload) as resp:
                        text = await resp.text()
                        if resp.status != 200:
                            logger.error("Server酱推送失败(状态码=%s): %s", resp.status, text)
                        else:
                            logger.info("Server酱推送成功: %s", text)
                            return True
                except asyncio.TimeoutError:
                    logger.error("Server酱推送超时，重试次数: %s/%s", attempt, self.max_retries)
                except aiohttp.ClientError as exc:
                    logger.error("Server酱推送网络错误: %s (重试 %s/%s)", exc, attempt, self.max_retries)

                if attempt < self.max_retries:
                    await asyncio.sleep(2 * attempt)

        logger.error("Server酱推送最终失败，已超过最大重试次数")
        return False


__all__ = ["WechatPusher"]

