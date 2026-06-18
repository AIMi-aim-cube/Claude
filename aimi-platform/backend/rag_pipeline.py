"""
AIMi — RAG Pipeline (chatbot brain)
===================================
Retrieval-Augmented Generation over three live knowledge sources:

  1. Scraped financial news      (NewsScraper, refreshed every 5 min)
  2. Live signals & quotes       (SignalGenerator / MarketDataScraper)
  3. Curated education corpus    (AIMi's financial-education layer)

Embeddings: sentence-transformers if available, otherwise a hashing-TF
vectorizer fallback (zero extra deps, works offline). Vector store is
in-memory cosine search — swap for FAISS/Chroma/pgvector in production.

Answering: any OpenAI-compatible LLM endpoint (env LLM_API_URL), falling
back to an extractive template answer so the chatbot always responds.
"""

from __future__ import annotations
import os
import re
import math
import time
import logging
from dataclasses import dataclass

import numpy as np
import requests

from scraper import news, market_data
from signals import signal_generator, DISCLAIMER

log = logging.getLogger("aimi.rag")

LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "finllama")

EDUCATION_CORPUS = [
    ("Diversification", "Diversification spreads investments across assets whose returns are "
     "not perfectly correlated, reducing portfolio volatility without proportionally reducing "
     "expected return. A common starting point is mixing equities, bonds and real assets."),
    ("Sharpe ratio", "The Sharpe ratio measures excess return per unit of risk: "
     "(portfolio return − risk-free rate) / volatility. Above 1 is good, above 2 is excellent."),
    ("Value at Risk", "VaR estimates the maximum expected loss over a horizon at a confidence "
     "level. A 1-day 95% VaR of 2% means losses should exceed 2% on only ~1 day in 20. "
     "CVaR measures the average loss in that tail."),
    ("Compounding", "Compounding reinvests returns so growth accelerates over time. "
     "At 7% annual return, money doubles roughly every 10 years (rule of 72)."),
    ("Dollar-cost averaging", "Investing a fixed amount at regular intervals reduces timing "
     "risk: you buy more units when prices are low and fewer when high."),
    ("Risk profiles", "AIMi maps users to conservative, balanced, growth or aggressive "
     "profiles. Each sets a volatility target, position caps and an allocation method "
     "(min-volatility, risk-parity or max-Sharpe)."),
    ("Drawdown", "Maximum drawdown is the largest peak-to-trough decline of an equity curve. "
     "It tells you the worst historical loss an investor would have endured."),
    ("Bid-ask spread", "The spread between buy and sell quotes is an implicit trading cost; "
     "liquid large-caps have tight spreads, small-caps and exotic assets wider ones."),
]


# -------------------------------------------------------------- embeddings
class Embedder:
    def __init__(self):
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            log.info("RAG embedder: sentence-transformers MiniLM")
        except Exception:
            log.info("RAG embedder: hashing-TF fallback")

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is not None:
            return np.asarray(self._model.encode(texts, normalize_embeddings=True))
        return np.vstack([self._hash_vec(t) for t in texts])

    @staticmethod
    def _hash_vec(text: str, dim: int = 512) -> np.ndarray:
        vec = np.zeros(dim)
        tokens = re.findall(r"[a-z0-9']+", text.lower())
        for tok in tokens:
            vec[hash(tok) % dim] += 1.0
        for a, b in zip(tokens, tokens[1:]):                 # bigrams help a lot
            vec[hash(a + "_" + b) % dim] += 1.5
        n = np.linalg.norm(vec)
        return vec / n if n else vec


@dataclass
class Doc:
    text: str
    source: str
    meta: dict


class VectorStore:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.docs: list[Doc] = []
        self.matrix: np.ndarray | None = None

    def index(self, docs: list[Doc]):
        self.docs = docs
        self.matrix = self.embedder.encode([d.text for d in docs])

    def search(self, query: str, k: int = 4) -> list[tuple[Doc, float]]:
        if self.matrix is None or not len(self.docs):
            return []
        q = self.embedder.encode([query])[0]
        sims = self.matrix @ q
        top = np.argsort(-sims)[:k]
        return [(self.docs[i], float(sims[i])) for i in top if sims[i] > 0.05]


# ------------------------------------------------------------------- RAG
class RAGPipeline:
    REFRESH_S = 300
    _TICKER_RE = re.compile(r"\b\$?([A-Z]{1,5})\b")
    _KNOWN = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "JPM",
              "SPY", "QQQ", "BTC", "ETH", "VOO", "BRK"}

    def __init__(self):
        self.store = VectorStore(Embedder())
        self._last_refresh = 0.0
        self.refresh(force=True)

    def refresh(self, force: bool = False):
        if not force and time.time() - self._last_refresh < self.REFRESH_S:
            return
        docs = [Doc(f"{t}: {body}", "education", {"topic": t})
                for t, body in EDUCATION_CORPUS]
        for item in news.fetch_all():
            docs.append(Doc(item.text, f"news:{item.source}",
                            {"link": item.link, "published": item.published}))
        self.store.index(docs)
        self._last_refresh = time.time()
        log.info("RAG index refreshed: %d docs", len(docs))

    # ------------------------------------------------------------ answering
    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        self.refresh()
        question = question.strip()
        live = self._live_context(question)
        hits = self.store.search(question, k=4)
        context_blocks = live + [f"[{d.source}] {d.text}" for d, _ in hits]

        text = self._llm_answer(question, context_blocks, history) \
            or self._extractive_answer(question, context_blocks)

        return {
            "answer": text,
            "sources": [{"source": d.source, **d.meta, "relevance": round(s, 3)}
                        for d, s in hits],
            "live_data_used": bool(live),
            "disclaimer": DISCLAIMER,
        }

    def _live_context(self, question: str) -> list[str]:
        """Inject live quote + signal when the question mentions a ticker."""
        blocks = []
        tickers = {m for m in self._TICKER_RE.findall(question.upper())} & self._KNOWN
        for t in list(tickers)[:2]:
            try:
                q = market_data.quote(t)
                sig = signal_generator.generate(t)
                blocks.append(
                    f"[live] {t} trades at {q['price']} ({q['change_pct']:+.2f}% today). "
                    f"AIMi composite signal: {sig.direction} "
                    f"(conviction {sig.conviction:.0%}). {sig.rationale}")
            except Exception as exc:
                log.warning("live context failed for %s: %s", t, exc)
        return blocks

    def _llm_answer(self, question, context, history) -> str | None:
        if not LLM_API_URL:
            return None
        system = ("You are AIMi, an institutional-grade financial intelligence assistant. "
                  "Answer using ONLY the provided context. Be concise, numerate and clear. "
                  "Never give personalised financial advice; explain, educate, inform. "
                  f"Always respect this disclaimer: {DISCLAIMER}\n\nContext:\n"
                  + "\n".join(context))
        msgs = [{"role": "system", "content": system}]
        for h in (history or [])[-6:]:
            msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        msgs.append({"role": "user", "content": question})
        try:
            r = requests.post(
                LLM_API_URL.rstrip("/") + "/v1/chat/completions",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                json={"model": LLM_MODEL, "messages": msgs,
                      "temperature": 0.3, "max_tokens": 400},
                timeout=45)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.warning("LLM endpoint failed: %s", exc)
            return None

    @staticmethod
    def _extractive_answer(question: str, context: list[str]) -> str:
        if not context:
            return ("I couldn't find anything relevant in my current knowledge base. "
                    "Try asking about markets, portfolio concepts, or a major ticker "
                    "like AAPL or SPY.")
        lead = context[0]
        extra = f" Also relevant: {context[1].split('] ', 1)[-1][:200]}" if len(context) > 1 else ""
        return f"{lead.split('] ', 1)[-1]}{extra}"


rag = RAGPipeline()
