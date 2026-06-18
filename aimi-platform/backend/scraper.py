"""
AIMi — Data Scraper
===================
Two pipelines:

  MarketDataScraper — OHLCV prices + live quotes (yfinance, with a
                      deterministic synthetic fallback for offline/demo).
  NewsScraper       — financial news headlines from public RSS feeds,
                      cleaned and deduplicated. Feeds both:
                        • the FinLlama sentiment engine (trading signals)
                        • the RAG knowledge base (chatbot answers)

Everything is cached in-memory with TTL so the live dashboard can poll
without hammering sources.
"""

from __future__ import annotations
import time
import html
import hashlib
import logging
import re
from dataclasses import dataclass, asdict
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("aimi.scraper")

# ----------------------------------------------------------------- caching
_CACHE: dict[str, tuple[float, object]] = {}

def _cached(key: str, ttl: float, fn):
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < ttl:
        return _CACHE[key][1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


# ------------------------------------------------------------ market data
class MarketDataScraper:
    """OHLCV history + live quotes. yfinance if installed, synthetic otherwise."""

    def __init__(self):
        try:
            import yfinance  # noqa: F401
            self._yf = True
        except ImportError:
            self._yf = False
            log.warning("yfinance not installed — using synthetic demo data")

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        key = f"hist:{ticker}:{period}:{interval}"
        return _cached(key, ttl=300, fn=lambda: self._fetch_history(ticker, period, interval))

    def quote(self, ticker: str) -> dict:
        key = f"quote:{ticker}"
        return _cached(key, ttl=15, fn=lambda: self._fetch_quote(ticker))

    def quotes(self, tickers: list[str]) -> list[dict]:
        return [self.quote(t) for t in tickers]

    # -- implementations ---------------------------------------------------
    def _fetch_history(self, ticker, period, interval) -> pd.DataFrame:
        if self._yf:
            try:
                import yfinance as yf
                df = yf.Ticker(ticker).history(period=period, interval=interval)
                if not df.empty:
                    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    return df
            except Exception as exc:
                log.warning("yfinance failed for %s: %s", ticker, exc)
        return self._synthetic(ticker, period, interval)

    def _fetch_quote(self, ticker) -> dict:
        df = self.history(ticker, period="5d", interval="1d")
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        return {
            "ticker": ticker.upper(),
            "price": round(last, 2),
            "change": round(last - prev, 2),
            "change_pct": round((last / prev - 1) * 100, 2),
            "volume": int(df["volume"].iloc[-1]),
            "ts": int(time.time()),
        }

    @staticmethod
    def _synthetic(ticker, period, interval) -> pd.DataFrame:
        """Deterministic geometric-Brownian demo series (seeded by ticker)."""
        n = {"1mo": 22, "3mo": 66, "6mo": 132, "1y": 252, "2y": 504, "5y": 1260}.get(period, 252)
        seed = int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        mu, sigma = 0.08 / 252, 0.20 / np.sqrt(252)
        rets = rng.normal(mu, sigma, n)
        close = 100 * np.exp(np.cumsum(rets))
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
        intraday = np.abs(rng.normal(0, sigma, n)) * close
        return pd.DataFrame({
            "open": close * (1 + rng.normal(0, sigma / 2, n)),
            "high": close + intraday,
            "low": close - intraday,
            "close": close,
            "volume": rng.integers(1e6, 5e7, n).astype(float),
        }, index=idx)


# ---------------------------------------------------------------- news/RSS
RSS_FEEDS = {
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "cnbc_markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "ft_markets": "https://www.ft.com/markets?format=rss",
    "investing": "https://www.investing.com/rss/news_25.rss",
}

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    published: str
    tickers: list

    def to_dict(self):
        return asdict(self)

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}".strip()


class NewsScraper:
    HEADERS = {"User-Agent": "AIMi-Research/1.0 (+https://chataimi.ai)"}

    def fetch_all(self, limit_per_feed: int = 15) -> list[NewsItem]:
        return _cached("news:all", ttl=300,
                       fn=lambda: self._fetch_feeds(limit_per_feed))

    def for_ticker(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        t = ticker.upper()
        items = [n for n in self.fetch_all() if t in n.tickers or t in n.title.upper()]
        return items[:limit]

    def _fetch_feeds(self, limit) -> list[NewsItem]:
        items, seen = [], set()
        for source, url in RSS_FEEDS.items():
            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=10)
                resp.raise_for_status()
                for item in self._parse_rss(resp.text, source)[:limit]:
                    key = hashlib.md5(item.title.lower().encode()).hexdigest()
                    if key not in seen:
                        seen.add(key)
                        items.append(item)
            except Exception as exc:
                log.warning("Feed %s failed: %s", source, exc)
        if not items:  # offline fallback so demos never break
            items = self._demo_items()
        return items

    def _parse_rss(self, xml_text: str, source: str) -> list[NewsItem]:
        out = []
        try:
            root = ElementTree.fromstring(xml_text)
            for it in root.iter("item"):
                title = self._clean(it.findtext("title", ""))
                summary = self._clean(it.findtext("description", ""))[:400]
                out.append(NewsItem(
                    title=title,
                    summary=summary,
                    link=it.findtext("link", "") or "",
                    source=source,
                    published=it.findtext("pubDate", "") or "",
                    tickers=self._extract_tickers(title + " " + summary),
                ))
        except ElementTree.ParseError as exc:
            log.warning("RSS parse error (%s): %s", source, exc)
        return out

    @staticmethod
    def _clean(text: str) -> str:
        return html.unescape(_TAG_RE.sub("", text or "")).strip()

    @staticmethod
    def _extract_tickers(text: str) -> list:
        # $AAPL style or (NASDAQ: AAPL) style
        cashtags = re.findall(r"\$([A-Z]{1,5})\b", text)
        exch = re.findall(r"\((?:NYSE|NASDAQ|LSE|AMEX):\s*([A-Z.]{1,6})\)", text)
        return sorted(set(cashtags + exch))

    @staticmethod
    def _demo_items() -> list[NewsItem]:
        demo = [
            ("Markets rally as inflation cools more than expected",
             "Equities surged after CPI data showed inflation easing, boosting rate-cut hopes."),
            ("Tech earnings beat estimates, AI spending accelerates",
             "Mega-cap technology firms reported record profits driven by AI infrastructure demand."),
            ("Oil declines on supply glut warning",
             "Crude fell 3% after IEA flagged rising inventories and weaker demand growth."),
        ]
        return [NewsItem(t, s, "", "demo", "", []) for t, s in demo]


market_data = MarketDataScraper()
news = NewsScraper()
