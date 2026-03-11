import logging
from typing import List

from openai import AsyncOpenAI

from .rss_fetcher import Article


logger = logging.getLogger(__name__)


class ContentSummarizer:
    """使用 OpenAI GPT-4o-mini 从候选文章中选出最重要的 3-5 条并输出中文摘要。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str = "gpt-4o-mini") -> None:
        client_kwargs: dict = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)
        self.model = model

    async def summarize(self, articles: List[Article], max_items: int = 5) -> List[dict]:
        """调用GPT接口，对文章进行重要性排序并生成简洁摘要。

        返回格式:
        [
          {
            "title": "...",
            "summary": "...",
            "link": "...",
            "source": "...",
            "category": "..."
          },
          ...
        ]
        """
        if not articles:
            logger.warning("没有可供总结的文章")
            return []

        # 为避免 prompt 过长，只取最近的前 N 条文章作为候选
        candidates = articles[:30]

        items_text = []
        for idx, a in enumerate(candidates, start=1):
            pub = a.published.isoformat() if a.published else "未知时间"
            items_text.append(
                f"{idx}. [来源] {a.source_name} | [分类] {a.category} | [时间] {pub}\n"
                f"标题: {a.title}\n"
                f"摘要: {a.summary}\n"
                f"链接: {a.link}\n"
            )

        system_prompt = (
            "你是一个专业的AI新闻编辑，擅长从大量资讯中选出最重要、最值得关注的内容。\n"
            "现在给你过去24小时内与人工智能相关的新闻列表，请你：\n"
            "1. 选出其中最重要、最有代表性的3-5条新闻（按重要性排序）\n"
            "2. 每条生成不超过50字的精炼中文摘要\n"
            "3. 尽量覆盖不同来源和话题\n"
            "4. 输出严格使用JSON数组格式，每个元素包含: title, summary, link, source, category 五个字段\n"
            "5. 不要输出任何额外说明或文字，只输出JSON数组\n"
        )

        user_prompt = "以下是候选新闻列表：\n\n" + "\n".join(items_text)

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("调用OpenAI GPT接口失败: %s", exc)
            return []

        content = resp.choices[0].message.content or ""

        import json

        try:
            result = json.loads(content)
            if not isinstance(result, list):
                raise ValueError("返回结果不是列表")
        except Exception as exc:  # noqa: BLE001
            logger.error("解析GPT返回JSON失败: %s; 原始内容: %s", exc, content)
            return []

        cleaned: List[dict] = []
        for item in result[:max_items]:
            try:
                cleaned.append(
                    {
                        "title": str(item.get("title", "")).strip(),
                        "summary": str(item.get("summary", "")).strip(),
                        "link": str(item.get("link", "")).strip(),
                        "source": str(item.get("source", "")).strip(),
                        "category": str(item.get("category", "")).strip(),
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        logger.info("成功从GPT获得 %d 条摘要结果", len(cleaned))
        return cleaned


__all__ = ["ContentSummarizer"]

