"""
AIMi — API Server (chataimi.ai backend)
=======================================
Run:  uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs
Dashboard: http://localhost:8000/  (serves frontend/dashboard.html)

Endpoints
---------
GET  /api/quote/{ticker}            live quote
GET  /api/history/{ticker}          OHLCV history
GET  /api/signal/{ticker}           composite trading signal
POST /api/signals/scan              scan a watchlist
POST /api/portfolio/build           portfolio + risk report
POST /api/backtest                  run/compare strategies
GET  /api/news                      scraped headlines + FinLlama sentiment
POST /api/sentiment                 FinLlama on arbitrary text
POST /api/chat                      RAG chatbot (text)
POST /api/voice                     RAG chatbot (audio upload or text)
POST /api/funnel/track              conversion funnel events
GET  /api/funnel/report             funnel analytics
WS   /ws/live                       live quotes + signals stream
"""

from __future__ import annotations
import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from scraper import market_data, news
from finllama_wrapper import finllama
from strategies import get_strategy, STRATEGY_REGISTRY
from backtest import Backtester
from portfolio import PortfolioBuilder, RISK_PROFILES
from signals import signal_generator
from rag_pipeline import rag
from voice import voice_chat
from funnel import funnel

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="AIMi API", version="0.1.0",
              description="AI-powered financial intelligence — chataimi.ai")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "SPY", "TSLA"]


# ------------------------------------------------------------- request models
class ScanRequest(BaseModel):
    tickers: list[str] = DEFAULT_WATCHLIST

class PortfolioRequest(BaseModel):
    tickers: list[str]
    risk_profile: str = "balanced"      # conservative|balanced|growth|aggressive
    period: str = "1y"

class BacktestRequest(BaseModel):
    ticker: str
    strategy: str = "momentum"          # or "all" to compare
    period: str = "2y"
    initial_capital: float = 100_000
    params: dict = {}

class SentimentRequest(BaseModel):
    texts: list[str]

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    user_id: str | None = None

class TrackRequest(BaseModel):
    user_id: str | None = None
    event: str
    props: dict = {}
    source: str | None = None


# -------------------------------------------------------------------- market
@app.get("/api/quote/{ticker}")
def quote(ticker: str):
    return market_data.quote(ticker)

@app.get("/api/history/{ticker}")
def history(ticker: str, period: str = "6mo", interval: str = "1d"):
    df = market_data.history(ticker, period, interval)
    return {"ticker": ticker.upper(),
            "bars": [{"t": str(i.date()), "o": round(r.open, 2), "h": round(r.high, 2),
                      "l": round(r.low, 2), "c": round(r.close, 2), "v": int(r.volume)}
                     for i, r in df.iterrows()]}


# ------------------------------------------------------------------- signals
@app.get("/api/signal/{ticker}")
def signal(ticker: str):
    return signal_generator.generate(ticker).to_dict()

@app.post("/api/signals/scan")
def scan(req: ScanRequest):
    return {"signals": signal_generator.scan(req.tickers[:10])}


# ----------------------------------------------------------------- portfolio
@app.post("/api/portfolio/build")
def build_portfolio(req: PortfolioRequest):
    import pandas as pd
    closes = {t.upper(): market_data.history(t, req.period)["close"]
              for t in req.tickers[:20]}
    prices = pd.DataFrame(closes).dropna()
    return PortfolioBuilder().build(prices, req.risk_profile)

@app.get("/api/portfolio/profiles")
def profiles():
    return RISK_PROFILES


# ------------------------------------------------------------------ backtest
@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    df = market_data.history(req.ticker, req.period)
    bt = Backtester(initial_capital=req.initial_capital)
    if req.strategy == "all":
        strats = [get_strategy(n) for n in ("momentum", "mean_reversion", "breakout")]
        return bt.compare(strats, df, req.ticker.upper())
    return bt.run(get_strategy(req.strategy, **req.params), df,
                  req.ticker.upper()).to_dict()

@app.get("/api/strategies")
def strategies():
    return {"strategies": list(STRATEGY_REGISTRY)}


# -------------------------------------------------------- news & sentiment
@app.get("/api/news")
def get_news(ticker: str | None = None, limit: int = 12):
    items = news.for_ticker(ticker, limit) if ticker else news.fetch_all()[:limit]
    out = []
    for n in items:
        s = finllama.analyze(n.text)
        out.append({**n.to_dict(), "sentiment": s.to_dict()})
    return {"news": out}

@app.post("/api/sentiment")
def sentiment(req: SentimentRequest):
    return finllama.aggregate(req.texts[:50])


# --------------------------------------------------------------- chat & voice
@app.post("/api/chat")
def chat(req: ChatRequest):
    if req.user_id:
        funnel.track(req.user_id, "chat_message")
    return rag.answer(req.message, history=req.history)

@app.post("/api/voice")
async def voice(text: str | None = Form(None),
                audio: UploadFile | None = File(None),
                user_id: str | None = Form(None)):
    audio_bytes = await audio.read() if audio else None
    if user_id:
        funnel.track(user_id, "voice_used")
    return voice_chat(text=text, audio_bytes=audio_bytes,
                      filename=audio.filename if audio else "audio.webm")


# -------------------------------------------------------------------- funnel
@app.post("/api/funnel/track")
def track(req: TrackRequest):
    return funnel.track(req.user_id, req.event, req.props, req.source)

@app.get("/api/funnel/report")
def funnel_report(hours: float = 720):
    return funnel.funnel_report(hours)


# --------------------------------------------------------------- live stream
@app.websocket("/ws/live")
async def live(ws: WebSocket):
    """Pushes quotes every 5s and a rotating fresh signal every 30s."""
    await ws.accept()
    watchlist = DEFAULT_WATCHLIST.copy()
    i, tick = 0, 0
    try:
        # client may send {"watchlist": [...]} at any time
        async def reader():
            nonlocal watchlist
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if isinstance(data.get("watchlist"), list):
                        watchlist = [t.upper() for t in data["watchlist"]][:10] or watchlist
                except json.JSONDecodeError:
                    pass
        reader_task = asyncio.create_task(reader())

        while True:
            quotes = await asyncio.to_thread(market_data.quotes, watchlist)
            payload = {"type": "quotes", "data": quotes}
            if tick % 6 == 0:  # every ~30s, refresh one signal
                t = watchlist[i % len(watchlist)]
                sig = await asyncio.to_thread(signal_generator.generate, t)
                payload["signal"] = sig.to_dict()
                i += 1
            await ws.send_json(payload)
            tick += 1
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()


# ------------------------------------------------------------------ frontend
@app.get("/")
def dashboard():
    return FileResponse("../frontend/dashboard.html")
