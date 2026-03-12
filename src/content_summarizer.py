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

    async def summarize(self, articles: List[Article], max_items: int = 15) -> List[dict]:
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
        candidates = articles[:50]

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
            "现在给你过去24小时内与人工智能相关的新闻列表，请你严格遵守以下要求：\n"
            f"1) 从中选出最重要、最有代表性的 10-15 条（按重要性排序，优先“大事件/重要发布/政策监管/融资并购/产品更新/研究突破”）\n"
            "2) 输出必须是【简体中文】；如原文标题/摘要为英文，请翻译成中文（保留专有名词/机构名可用英文）\n"
            "3) 每条生成不超过 50 字的精炼中文摘要\n"
            "4) 尽量覆盖不同来源和话题，不要只集中在某一家（例如 OpenAI）\n"
            "5) 输出严格使用 JSON 数组格式，每个元素包含：title, summary, link, source, category 五个字段\n"
            "6) 不要输出任何额外说明或文字，只输出 JSON 数组\n"
        )

        user_prompt = "以下是候选新闻列表：\n\n" + "\n".join(items_text)

        result = await self._call_and_parse_json(system_prompt, user_prompt)
        if result is None:
            return []
        # 若模型输出出现明显英文占比过高，进行一次纠偏重试（只在必要时触发，控制成本）
        if self._looks_english_heavy(result):
            logger.warning("检测到摘要结果英文占比偏高，触发一次纠偏重试。")
            fix_prompt = (
                "你刚才的输出包含较多英文，不符合要求。\n"
                "请你重新输出同样格式的 JSON 数组，确保 title 和 summary 都是简体中文，"
                "必要时翻译英文标题/摘要为中文（保留专有名词）。\n"
                "再次强调：只输出 JSON 数组。"
            )
            result = await self._call_and_parse_json(system_prompt + "\n" + fix_prompt, user_prompt)
            if result is None:
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

    async def _call_and_parse_json(self, system_prompt: str, user_prompt: str) -> list | None:
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=900,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("调用OpenAI GPT接口失败: %s", exc)
            return None

        content = resp.choices[0].message.content or ""

        import json

        try:
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                raise ValueError("返回结果不是列表")
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.error("解析GPT返回JSON失败: %s; 原始内容: %s", exc, content)
            return None

    @staticmethod
    def _looks_english_heavy(items: list) -> bool:
        """粗略检测输出是否英文占比过高，用于触发一次纠偏重试。"""
        if not items:
            return False

        def ascii_ratio(s: str) -> float:
            if not s:
                return 0.0
            ascii_count = sum(1 for ch in s if ord(ch) < 128)
            return ascii_count / max(len(s), 1)

        checks = 0
        hits = 0
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            for key in ("title", "summary"):
                text = str(item.get(key, ""))
                if not text:
                    continue
                checks += 1
                if ascii_ratio(text) > 0.7:
                    hits += 1

        return checks > 0 and hits / checks >= 0.5


__all__ = ["ContentSummarizer"]

