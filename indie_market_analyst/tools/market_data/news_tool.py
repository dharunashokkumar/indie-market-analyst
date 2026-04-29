"""Indian-market news + lightweight aggregate sentiment.

Free sources only:
  - RSS feeds from Moneycontrol, Economic Times, Livemint, Business Standard
    (no API key, public XML).
  - Marketaux / NewsAPI optional, activated only if MARKETAUX_API_KEY /
    NEWSAPI_KEY is set in the environment.

Sentiment is a deterministic keyword tally (bull/bear/neutral) computed here
in Python so the LLM cannot hallucinate mood numbers.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field

_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_RSS_SOURCES: dict[str, str] = {
    "moneycontrol_markets": "https://www.moneycontrol.com/rss/marketreports.xml",
    "moneycontrol_business": "https://www.moneycontrol.com/rss/business.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "livemint_markets": "https://www.livemint.com/rss/markets",
    "bs_markets": "https://www.business-standard.com/rss/markets-106.rss",
    "google_news_markets": (
        "https://news.google.com/rss/search?"
        "q=India%20stock%20market%20OR%20Nifty%20OR%20Sensex%20when%3A1d"
        "&hl=en-IN&gl=IN&ceid=IN%3Aen"
    ),
}

_BULL = {
    "surge", "surges", "rally", "rallies", "gain", "gains", "jump", "jumps",
    "soar", "soars", "rise", "rises", "rose", "up", "climb", "climbs",
    "beats", "beat", "upgrade", "bullish", "record high", "high", "strong",
    "outperform", "profit", "profits",
}
_BEAR = {
    "plunge", "plunges", "slump", "slumps", "fall", "falls", "fell", "drop",
    "drops", "tumble", "tumbles", "slide", "slides", "decline", "declines",
    "down", "crash", "crashes", "miss", "misses", "downgrade", "bearish",
    "low", "weak", "underperform", "loss", "losses", "warning",
}


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    link: str
    published_utc: str | None
    summary: str = ""
    source: str
    sentiment: str = Field(description="bull | bear | neutral")


class NewsDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[NewsItem]
    total: int
    bullish: int
    bearish: int
    neutral: int
    overall_sentiment: str = Field(
        description="bullish | bearish | mixed | neutral — aggregate read"
    )
    sentiment_score: float = Field(
        description="(bullish - bearish) / total, in [-1.0, 1.0]"
    )
    as_of_utc: str
    sources_used: list[str]


_WORD_RE = re.compile(r"[a-zA-Z]+")


def _label(text: str) -> str:
    words = {w.lower() for w in _WORD_RE.findall(text)}
    b = len(words & _BULL)
    d = len(words & _BEAR)
    if b > d and b > 0:
        return "bull"
    if d > b and d > 0:
        return "bear"
    return "neutral"


def _parse_rfc822(s: str | None) -> str | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except Exception:
        return None


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _fetch_rss(url: str, source: str, topic: str | None, client: httpx.Client) -> list[NewsItem]:
    try:
        r = client.get(url, timeout=12.0)
        r.raise_for_status()
    except Exception:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    items: list[NewsItem] = []
    for it in root.iter("item"):
        title = _strip_html((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        desc = _strip_html((it.findtext("description") or "").strip())
        pub = _parse_rfc822(it.findtext("pubDate"))
        if not title or not link:
            continue
        if topic:
            haystack = f"{title} {desc}".lower()
            if topic.lower() not in haystack:
                continue
        items.append(
            NewsItem(
                title=title,
                link=link,
                published_utc=pub,
                summary=desc[:280],
                source=source,
                sentiment=_label(f"{title}. {desc}"),
            )
        )
    return items


def _fetch_marketaux(topic: str | None, limit: int) -> list[NewsItem]:
    key = os.getenv("MARKETAUX_API_KEY")
    if not key:
        return []
    params = {
        "api_token": key,
        "countries": "in",
        "language": "en",
        "limit": min(limit, 50),
    }
    if topic:
        params["search"] = topic
    try:
        r = httpx.get("https://api.marketaux.com/v1/news/all", params=params, timeout=12.0)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out: list[NewsItem] = []
    for row in data.get("data", []):
        title = (row.get("title") or "").strip()
        link = (row.get("url") or "").strip()
        desc = (row.get("description") or row.get("snippet") or "").strip()
        pub = row.get("published_at")
        if pub:
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(UTC).isoformat()
            except Exception:
                pub = None
        if not title or not link:
            continue
        out.append(
            NewsItem(
                title=title,
                link=link,
                published_utc=pub,
                summary=desc[:280],
                source="marketaux",
                sentiment=_label(f"{title}. {desc}"),
            )
        )
    return out


def _fetch_newsapi(topic: str | None, limit: int) -> list[NewsItem]:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return []
    params = {
        "apiKey": key,
        "language": "en",
        "pageSize": min(limit, 50),
        "q": topic or "India stock market OR Nifty OR Sensex",
        "sortBy": "publishedAt",
    }
    try:
        r = httpx.get("https://newsapi.org/v2/everything", params=params, timeout=12.0)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out: list[NewsItem] = []
    for row in data.get("articles", []):
        title = (row.get("title") or "").strip()
        link = (row.get("url") or "").strip()
        desc = (row.get("description") or "").strip()
        pub = row.get("publishedAt")
        if pub:
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(UTC).isoformat()
            except Exception:
                pub = None
        if not title or not link:
            continue
        out.append(
            NewsItem(
                title=title,
                link=link,
                published_utc=pub,
                summary=desc[:280],
                source="newsapi",
                sentiment=_label(f"{title}. {desc}"),
            )
        )
    return out


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        key = re.sub(r"\W+", "", it.title.lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _sort_recent(items: list[NewsItem]) -> list[NewsItem]:
    def ts(it: NewsItem) -> str:
        return it.published_utc or ""
    return sorted(items, key=ts, reverse=True)


def fetch_market_news(topic: str = "", limit: int = 12) -> NewsDigest:
    """Fetch recent Indian-market headlines with aggregate sentiment."""
    limit = max(1, min(int(limit), 30))
    topic_q = topic.strip() or None
    collected: list[NewsItem] = []
    sources_used: list[str] = []

    with httpx.Client(headers=_UA, follow_redirects=True) as c:
        for name, url in _RSS_SOURCES.items():
            batch = _fetch_rss(url, name, topic_q, c)
            if batch:
                sources_used.append(name)
                collected.extend(batch)

    ma = _fetch_marketaux(topic_q, limit)
    if ma:
        sources_used.append("marketaux")
        collected.extend(ma)

    na = _fetch_newsapi(topic_q, limit)
    if na:
        sources_used.append("newsapi")
        collected.extend(na)

    # Playwright fallback: only when cheap sources yielded nothing. Disable
    # with NEWS_PLAYWRIGHT_FALLBACK=0 for environments where chromium isn't
    # installed (CI, minimal containers).
    if not collected and os.getenv("NEWS_PLAYWRIGHT_FALLBACK", "1") == "1":
        try:
            from indie_market_analyst.tools.market_data.playwright_scraper import (
                scrape_deep,
            )

            digest = scrape_deep(topic=topic_q, limit_per_site=3)
            if digest.items:
                sources_used.extend(f"pw:{s}" for s in digest.sources_used)
                collected.extend(digest.items)
        except Exception:
            # Scraper must never break the RSS path.
            pass

    items = _sort_recent(_dedupe(collected))[:limit]
    bulls = sum(1 for i in items if i.sentiment == "bull")
    bears = sum(1 for i in items if i.sentiment == "bear")
    neut = sum(1 for i in items if i.sentiment == "neutral")
    total = len(items)
    score = 0.0 if total == 0 else round((bulls - bears) / total, 3)
    if total == 0:
        overall = "neutral"
    elif score >= 0.25:
        overall = "bullish"
    elif score <= -0.25:
        overall = "bearish"
    elif bulls > 0 and bears > 0:
        overall = "mixed"
    else:
        overall = "neutral"

    return NewsDigest(
        items=items,
        total=total,
        bullish=bulls,
        bearish=bears,
        neutral=neut,
        overall_sentiment=overall,
        sentiment_score=score,
        as_of_utc=datetime.now(UTC).isoformat(),
        sources_used=sources_used,
    )


@function_tool
def get_market_news(topic: str = "", limit: int = 12) -> NewsDigest:
    """Fetch recent Indian-market headlines with aggregate sentiment.

    Args:
        topic: optional filter keyword (e.g. ``"nifty"``, ``"reliance"``,
            ``"rbi"``). Empty string returns the general markets feed.
        limit: max items to return (1–30).

    Returns a NewsDigest with per-item bull/bear/neutral labels plus an
    aggregate ``overall_sentiment`` computed deterministically from counts.
    """
    return fetch_market_news(topic=topic, limit=limit)


TOOLS = [get_market_news]
