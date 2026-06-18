# AIMi Full Dashboard

Deployable Next.js dashboard for AIMi / ChatAIMi.

## What is included

- Tier 1–5 gated UI
- Ask AIMi chat screen
- Learn / LMS interface
- Insights feed
- Tier 4–5 signals dashboard
- Tier 5 FinLLAMA Quant Intelligence dashboard
- Regime AI and portfolio risk UI
- Broker redirect / hand-off screen
- Admin dashboard
- Compliance and audit logs
- Live-data API routes with fallbacks
- Firebase-ready configuration
- Gemini-ready chat route

## Open locally

```bash
npm install
npm run dev
```

Then open:

```text
http://localhost:3000
```

## Live data

The app is wired to live data through Next.js API routes:

- `/api/market` uses Yahoo Finance chart data at runtime and falls back to demo data if blocked.
- `/api/news` uses Finnhub if `FINNHUB_API_KEY` is set and falls back to AIMi demo intelligence.
- `/api/chat` uses Gemini if `GOOGLE_GENERATIVE_AI_API_KEY` is set and falls back to a safe AIMi response.
- `/api/signals` currently returns structured signal objects; replace this with your FinLLAMA signal service.
- `/api/admin` returns operational metrics; replace this with Firestore/BigQuery.

Copy `.env.example` to `.env.local` and add keys.

## Recommended domains

- `aim-cube.com` = parent company / investor website
- `chataimi.ai` = user-facing product
- `app.chataimi.ai` = authenticated dashboard later

## Production integration path

1. Add Firebase Auth in the login layer.
2. Store users, tiers, subscriptions, onboarding and disclosures in Firestore.
3. Connect Stripe webhooks to tier entitlement changes.
4. Replace `/api/signals` with FinLLAMA signal service.
5. Replace `/api/admin` with Firestore/BigQuery analytics.
6. Add broker redirect tracking parameters.
7. Add Cloud Logging / audit export.
