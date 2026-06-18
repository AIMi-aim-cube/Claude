"""
AIMi — Trading Signal Generator
===============================
Composite signals: technical strategies (60%) blended with FinLlama news
sentiment (40%). Each signal carries direction, conviction, contributing
factors and a plain-English rationale — the same structure surfaced on the
dashboard and read aloud by the voice assistant.

NOTE: Output is research/educational intelligence, not personalised
financial advice. The disclaimer is attached to every payload.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field, asdict

from strategies import MomentumStrategy, MeanReversionStrategy, BreakoutStrategy
from scraper import market_data, news
from finllama_wrapper import finllama

log = logging.getLogger("aimi.signals")

DISCLAIMER = ("AIMi signals are research and education tools, "
              "not personalised investment advice. Capital at risk.")

TECH_WEIGHT, SENT_WEIGHT = 0.6, 0.4
_SIGNAL_VALUE = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}


@dataclass
class TradingSignal:
    ticker: str
    direction: str            # STRONG BUY / BUY / HOLD / SELL / STRONG SELL
    conviction: float         # 0..1
    composite_score: float    # -1..1
    technical: dict = field(default_factory=dict)
    sentiment: dict = field(default_factory=dict)
    rationale: str = ""
    price: float = 0.0
    ts: int = 0
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)


class SignalGenerator:
    def __init__(self):
        self.strategies = [MomentumStrategy(), MeanReversionStrategy(), BreakoutStrategy()]

    def generate(self, ticker: str, period: str = "1y") -> TradingSignal:
        df = market_data.history(ticker, period=period)
        quote = market_data.quote(ticker)

        # --- technical leg -------------------------------------------------
        tech_votes, tech_detail = [], {}
        for strat in self.strategies:
            try:
                res = strat.generate(df)
                val = _SIGNAL_VALUE[res.last_signal] * max(res.confidence, 0.3)
                tech_votes.append(val)
                tech_detail[strat.name] = {"signal": res.last_signal,
                                           "confidence": round(res.confidence, 2)}
            except Exception as exc:
                log.warning("%s failed on %s: %s", strat.name, ticker, exc)
        tech_score = sum(tech_votes) / len(tech_votes) if tech_votes else 0.0

        # --- sentiment leg (FinLlama over scraped headlines) ----------------
        headlines = [n.text for n in news.for_ticker(ticker)] or \
                    [n.text for n in news.fetch_all()[:8]]
        agg = finllama.aggregate(headlines[:10])
        sent_score = agg["score"]

        # --- blend ----------------------------------------------------------
        composite = TECH_WEIGHT * tech_score + SENT_WEIGHT * sent_score
        direction = self._bucket(composite)
        conviction = round(min(abs(composite) * 1.5, 1.0), 2)

        rationale = self._explain(ticker, direction, tech_detail, agg)
        return TradingSignal(
            ticker=ticker.upper(), direction=direction, conviction=conviction,
            composite_score=round(composite, 3),
            technical={"score": round(tech_score, 3), "strategies": tech_detail},
            sentiment={"score": sent_score, "label": agg["label"],
                       "headlines_analysed": agg["n"]},
            rationale=rationale, price=quote["price"], ts=int(time.time()),
        )

    def scan(self, tickers: list[str]) -> list[dict]:
        signals = [self.generate(t).to_dict() for t in tickers]
        return sorted(signals, key=lambda s: abs(s["composite_score"]), reverse=True)

    @staticmethod
    def _bucket(score: float) -> str:
        if score >= 0.5:  return "STRONG BUY"
        if score >= 0.15: return "BUY"
        if score <= -0.5: return "STRONG SELL"
        if score <= -0.15:return "SELL"
        return "HOLD"

    @staticmethod
    def _explain(ticker, direction, tech, agg) -> str:
        agree = [f"{k} says {v['signal']}" for k, v in tech.items()]
        return (f"{ticker.upper()}: {direction}. Technical view — {'; '.join(agree)}. "
                f"News sentiment is {agg['label']} ({agg['score']:+.2f}) "
                f"across {agg['n']} recent headlines.")


signal_generator = SignalGenerator()
