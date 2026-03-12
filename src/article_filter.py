"""
推送前过滤：只保留标题或摘要中包含 AI 行业关键词的文章。
"""
import logging
from typing import List

from .rss_fetcher import Article


logger = logging.getLogger(__name__)

# 默认关键词（当 config 未配置时使用）
DEFAULT_AI_KEYWORDS = [
    "ai", "大模型", "算力", "人工智能", "机器学习", "深度学习",
    "LLM", "GPT", "生成式", "神经网络", "NLP", "计算机视觉",
    "AIGC", "大语言模型", "智能体", "Agent",
]


def filter_by_ai_keywords(
    articles: List[Article],
    keywords: List[str] | None = None,
) -> List[Article]:
    """
    只保留标题或摘要中包含任一 AI 关键词的文章。
    关键词匹配不区分大小写（英文），中文按原样匹配。
    """
    kws = keywords or DEFAULT_AI_KEYWORDS
    if not kws:
        return articles

    filtered: List[Article] = []
    for a in articles:
        text = (a.title or "") + " " + (a.summary or "")
        if not text.strip():
            continue
        text_lower = text.lower()
        for kw in kws:
            if not kw:
                continue
            # 英文关键词不区分大小写
            if kw.isascii():
                if kw.lower() in text_lower:
                    filtered.append(a)
                    break
            else:
                if kw in text:
                    filtered.append(a)
                    break

    dropped = len(articles) - len(filtered)
    if dropped > 0:
        logger.info("按 AI 关键词过滤：保留 %d 条，过滤掉 %d 条", len(filtered), dropped)
    return filtered


__all__ = ["filter_by_ai_keywords", "DEFAULT_AI_KEYWORDS"]
