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

    async def summarize(
        self,
        articles: List[Article],
        max_items: int = 15,
        min_x_items: int = 2,
    ) -> List[dict]:
        """调用GPT接口，按质量与热度排序，精选 max_items 条，其中至少 min_x_items 条来自 X 平台。

        返回格式:
        [
          { "title": "...", "summary": "...", "link": "...", "source": "...", "category": "..." },
          ...
        ]
        """
        if not articles:
            logger.warning("没有可供总结的文章")
            return []

        # 为避免 prompt 过长，只取最近的前 N 条文章作为候选
        candidates = articles[:60]

        items_text = []
        for idx, a in enumerate(candidates, start=1):
            pub = a.published.isoformat() if a.published else "未知时间"
            items_text.append(
                f"{idx}. [来源] {a.source_name} | [分类] {a.category} | [时间] {pub}\n"
                f"标题: {a.title}\n"
                f"摘要: {a.summary}\n"
                f"链接: {a.link}\n"
            )

        x_requirement = (
            f"必须包含至少 {min_x_items} 条来源为「X 热门帖子」的内容（X 条目的摘要中带有点赞/转发/评论数，请按热度优先选取）。\n"
            if min_x_items > 0
            else ""
        )
        system_prompt = (
            "你是一个专业的AI新闻编辑，只处理与人工智能（AI）直接相关的内容。\n"
            "现在给你一批已初步筛选过的 AI 相关资讯（含新闻与 X 平台热帖），请你：\n"
            f"1) 按「文章质量」和「热度」综合排序，精选出恰好 {max_items} 条，只选与 AI/大模型/算力/人工智能/机器学习/生成式等强相关的内容。\n"
            + x_requirement
            + "2) 输出必须是【简体中文】；英文标题/摘要请翻译成中文（专有名词可保留英文）。\n"
            "3) 每条生成不超过 50 字的精炼中文摘要。\n"
            "4) 尽量覆盖不同来源和话题。\n"
            "5) 输出严格使用 JSON 数组格式，每个元素包含：title, summary, link, source, category 五个字段。\n"
            "6) 不要输出任何额外说明，只输出 JSON 数组。\n"
        )

        user_prompt = (
            "以下是候选列表（已过滤为 AI 相关），请按质量与热度排序后精选恰好 "
            + str(max_items)
            + " 条，且至少 "
            + str(min_x_items)
            + " 条来自「X 热门帖子」。\n\n"
            + "\n".join(items_text)
        )

        result = await self._call_and_parse_json(system_prompt, user_prompt, max_tokens=1200)
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

    async def _call_and_parse_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1200,
    ) -> list | None:
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
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

