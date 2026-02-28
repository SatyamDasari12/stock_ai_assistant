from __future__ import annotations

from dataclasses import dataclass
from typing import List

import feedparser

from utils.logging import logger


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str


def _fetch_rss_items(symbol: str, max_items: int = 5) -> List[NewsItem]:
    """
    Fetch recent RSS headlines that mention the given symbol.

    This is a lightweight, dependency‑friendly alternative to a full
    vector database. It filters generic Indian market feeds by symbol.
    """
    feeds = [
        "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "https://www.moneycontrol.com/rss/MCtopnews.xml",
    ]
    items: List[NewsItem] = []
    symbol_key = symbol.lower().split(".")[0]

    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                link = getattr(entry, "link", "")
                text = f"{title} {summary}".lower()
                if symbol_key in text:
                    items.append(NewsItem(title=title, summary=summary, link=link))
                    if len(items) >= max_items:
                        return items
        except Exception as exc:
            logger.exception(f"Failed to parse RSS feed {url}: {exc}")

    return items


def get_symbol_news_summaries(symbol: str, top_k: int = 5) -> List[str]:
    """
    Return a small list of human‑readable news summaries for the symbol.
    """
    items = _fetch_rss_items(symbol, max_items=top_k)
    return [f"{i.title} — {i.summary}" for i in items]


