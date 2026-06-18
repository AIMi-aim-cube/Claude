"""
AIMi — FinLlama Wrapper
=======================
Unified interface around FinLlama (a LLaMA model fine-tuned for financial
sentiment). Three execution backends, auto-selected:

  1. "hf"     — local HuggingFace transformers pipeline (GPU/CPU)
  2. "api"    — any OpenAI-compatible inference endpoint hosting FinLlama
  3. "lexicon"— dependency-free Loughran–McDonald-style fallback so the
                platform degrades gracefully when no model is available.

Output is always normalised to: {label, score, rationale}
  label ∈ {positive, negative, neutral},  score ∈ [-1, 1]
"""

from __future__ import annotations
import os
import re
import json
import logging
from dataclasses import dataclass, asdict
from typing import Iterable

import requests

log = logging.getLogger("aimi.finllama")

FINLLAMA_HF_MODEL = os.getenv("FINLLAMA_HF_MODEL", "roma2025/FinLlama-3-8B")
FINLLAMA_API_URL = os.getenv("FINLLAMA_API_URL", "")        # e.g. vLLM / TGI endpoint
FINLLAMA_API_KEY = os.getenv("FINLLAMA_API_KEY", "")

_PROMPT = (
    "You are FinLlama, a financial sentiment engine.\n"
    "Classify the sentiment of the following financial text strictly as JSON "
    'with keys "label" (positive|negative|neutral), "score" (-1 to 1), '
    '"rationale" (one sentence).\n\nText: {text}\n\nJSON:'
)

# Minimal Loughran–McDonald-flavoured lexicon for the offline fallback
_POS = {"beat", "beats", "growth", "record", "upgrade", "upgraded", "bullish", "surge",
        "rally", "outperform", "strong", "profit", "gain", "gains", "raised", "expands",
        "buyback", "dividend", "exceeds", "momentum", "breakout", "recovery"}
_NEG = {"miss", "misses", "downgrade", "downgraded", "bearish", "plunge", "selloff",
        "underperform", "weak", "loss", "losses", "cut", "cuts", "lawsuit", "fraud",
        "default", "bankruptcy", "recall", "warning", "decline", "drop", "crash",
        "investigation", "layoffs", "restructuring"}
_NEGATORS = {"not", "no", "never", "without", "fails", "failed"}


@dataclass
class SentimentResult:
    label: str
    score: float
    rationale: str
    backend: str

    def to_dict(self) -> dict:
        return asdict(self)


class FinLlamaWrapper:
    def __init__(self, backend: str | None = None):
        self.backend = backend or self._autodetect()
        self._pipe = None
        if self.backend == "hf":
            self._init_hf()
        log.info("FinLlama backend: %s", self.backend)

    # ---------------------------------------------------------------- setup
    def _autodetect(self) -> str:
        if FINLLAMA_API_URL:
            return "api"
        try:
            import transformers  # noqa: F401
            import torch         # noqa: F401
            return "hf"
        except ImportError:
            return "lexicon"

    def _init_hf(self):
        try:
            from transformers import pipeline
            self._pipe = pipeline(
                "text-generation",
                model=FINLLAMA_HF_MODEL,
                max_new_tokens=120,
                do_sample=False,
            )
        except Exception as exc:  # model unavailable -> degrade
            log.warning("HF init failed (%s); falling back to lexicon", exc)
            self.backend = "lexicon"

    # ------------------------------------------------------------- inference
    def analyze(self, text: str) -> SentimentResult:
        text = (text or "").strip()
        if not text:
            return SentimentResult("neutral", 0.0, "Empty input.", self.backend)
        try:
            if self.backend == "api":
                return self._via_api(text)
            if self.backend == "hf":
                return self._via_hf(text)
        except Exception as exc:
            log.warning("FinLlama %s backend failed (%s); using lexicon", self.backend, exc)
        return self._via_lexicon(text)

    def analyze_batch(self, texts: Iterable[str]) -> list[SentimentResult]:
        return [self.analyze(t) for t in texts]

    def aggregate(self, texts: Iterable[str]) -> dict:
        """Aggregate sentiment over many headlines -> one market-mood score."""
        results = self.analyze_batch(texts)
        if not results:
            return {"score": 0.0, "label": "neutral", "n": 0}
        score = sum(r.score for r in results) / len(results)
        label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
        return {"score": round(score, 3), "label": label, "n": len(results),
                "items": [r.to_dict() for r in results]}

    # -------------------------------------------------------------- backends
    def _via_api(self, text: str) -> SentimentResult:
        resp = requests.post(
            FINLLAMA_API_URL.rstrip("/") + "/v1/chat/completions",
            headers={"Authorization": f"Bearer {FINLLAMA_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "finllama",
                  "messages": [{"role": "user", "content": _PROMPT.format(text=text)}],
                  "temperature": 0.0, "max_tokens": 150},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return self._parse_json(raw, "api")

    def _via_hf(self, text: str) -> SentimentResult:
        out = self._pipe(_PROMPT.format(text=text))[0]["generated_text"]
        return self._parse_json(out.split("JSON:")[-1], "hf")

    def _via_lexicon(self, text: str) -> SentimentResult:
        words = re.findall(r"[a-z']+", text.lower())
        score, hits = 0.0, []
        for i, w in enumerate(words):
            s = 1.0 if w in _POS else -1.0 if w in _NEG else 0.0
            if s and i > 0 and words[i - 1] in _NEGATORS:
                s = -s
            if s:
                hits.append(w)
                score += s
        norm = max(-1.0, min(1.0, score / max(len(hits), 1) * min(len(hits), 3) / 3)) if hits else 0.0
        label = "positive" if norm > 0.15 else "negative" if norm < -0.15 else "neutral"
        rationale = f"Lexicon hits: {', '.join(hits[:6])}" if hits else "No sentiment-bearing terms."
        return SentimentResult(label, round(norm, 3), rationale, "lexicon")

    @staticmethod
    def _parse_json(raw: str, backend: str) -> SentimentResult:
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else {}
        return SentimentResult(
            label=data.get("label", "neutral"),
            score=float(data.get("score", 0.0)),
            rationale=data.get("rationale", ""),
            backend=backend,
        )


# Singleton used across the app
finllama = FinLlamaWrapper()
