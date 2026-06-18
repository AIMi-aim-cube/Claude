# AIMi Platform — chataimi.ai

AI-powered financial intelligence: trading strategies, FinLlama sentiment,
live data scraping, portfolio & risk analytics, backtesting, a RAG voice
chatbot, conversion funnel, and a live dashboard — in one runnable scaffold.

```
aimi-platform/
├── backend/
│   ├── main.py               FastAPI app — REST + WebSocket + serves dashboard
│   ├── strategies.py         5 strategies: momentum, mean-reversion, breakout,
│   │                         pairs trading, risk parity (one shared interface)
│   ├── finllama_wrapper.py   FinLlama sentiment (HF local / API / lexicon fallback)
│   ├── scraper.py            Market data (yfinance + synthetic fallback) and
│   │                         RSS news scraper feeding sentiment + RAG
│   ├── portfolio.py          Portfolio builder (min-vol / risk-parity / max-Sharpe
│   │                         by risk profile) + RiskAnalyzer (VaR, CVaR, Sharpe,
│   │                         Sortino, max drawdown, beta, Calmar, correlations)
│   ├── backtest.py           Vectorised backtester — next-bar execution, costs,
│   │                         slippage, trade log, strategy comparison vs buy&hold
│   ├── signals.py            Composite signals: 60% technical + 40% FinLlama news
│   ├── rag_pipeline.py       RAG over news + live quotes/signals + education corpus
│   ├── voice.py              STT (whisper/API/browser) → RAG → TTS voice loop
│   └── funnel.py             chataimi.ai conversion funnel: stages, lead scoring,
│                             contextual nudges, analytics (SQLite)
├── frontend/
│   └── dashboard.html        Live dashboard: WebSocket ticker tape, signal pulse
│                             gauge, charts, backtest lab, portfolio builder,
│                             news+sentiment, voice/text chat, funnel nudges
└── requirements.txt
```

## Quick start

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --reload --port 8000
# open http://localhost:8000  (dashboard)
# open http://localhost:8000/docs  (interactive API docs)
```

Works fully offline out of the box — when yfinance or RSS feeds are
unreachable it serves deterministic demo data, and FinLlama falls back to
a financial lexicon, so demos never break.

## Configuration (env vars)

| Variable           | Purpose                                              |
|--------------------|------------------------------------------------------|
| `FINLLAMA_API_URL` | OpenAI-compatible endpoint hosting FinLlama          |
| `FINLLAMA_HF_MODEL`| HuggingFace model id for local inference             |
| `LLM_API_URL/KEY`  | Chat LLM for RAG answer synthesis                    |
| `STT_API_URL/KEY`  | Server-side Whisper endpoint (browser STT otherwise) |

## Key API calls

```bash
# Composite trading signal (technical + FinLlama sentiment)
curl localhost:8000/api/signal/NVDA

# Portfolio with risk analysis
curl -X POST localhost:8000/api/portfolio/build -H 'Content-Type: application/json' \
  -d '{"tickers":["AAPL","MSFT","SPY","TSLA"],"risk_profile":"growth"}'

# Backtest (or "strategy":"all" to compare)
curl -X POST localhost:8000/api/backtest -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","strategy":"momentum","period":"2y"}'

# RAG chatbot
curl -X POST localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"What is the signal on AAPL and what does VaR mean?"}'

# Funnel analytics
curl localhost:8000/api/funnel/report
```

## Conversion funnel (chataimi.ai)

Stages: `visitor → engaged → signup → activated → trial → paid → enterprise_lead`.
The frontend fires events (`page_view`, `chat_message`, `signal_viewed`,
`backtest_run`, `portfolio_built`, …); the tracker promotes stages, scores
leads, and returns contextual nudges at value moments (e.g. after 3 chat
messages → signup prompt; after 2 signals viewed → trial prompt). Enterprise
prospects (score ≥ 40) surface in `/api/funnel/report` for the sales pipeline.

## Production hardening checklist

- Swap SQLite → Postgres; in-memory vector store → pgvector/Chroma/FAISS
- Replace random-search optimiser with cvxpy/scipy exact solvers
- Add auth (JWT), rate limiting, and per-tier feature gating
- Stream market data from a paid feed (Polygon/Refinitiv) instead of yfinance
- FCA/DIFC compliance review of all signal & disclaimer copy

---
*AIMi provides research and education, not personalised financial advice.
Capital at risk.*
