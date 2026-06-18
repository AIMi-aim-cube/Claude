# AIMi UI Structure

## Main navigation

1. Overview
2. Ask AIMi
3. Learn
4. Insights
5. Signals
6. FinLLAMA Quant
7. Broker Hand-off
8. Admin
9. Compliance

## Tier gating

- Tier 1: education, basic chat, beginner lessons, daily insight summaries.
- Tier 2: memory, investing principles, scenarios, expanded learning.
- Tier 3: illustrative portfolio logic, macro explanations, allocation intuition.
- Tier 4: market regime insights, weekly intelligence, signals intelligence.
- Tier 5: FinLLAMA, multi-strategy quant intelligence, portfolio risk, audit/replay.

## Live services

- Market data: `app/api/market/route.ts`
- News: `app/api/news/route.ts`
- AIMi chat: `app/api/chat/route.ts`
- Signals: `app/api/signals/route.ts`
- Admin metrics: `app/api/admin/route.ts`

## Key files

- `app/page.tsx` renders dashboard.
- `components/Dashboard.tsx` contains the full UI.
- `lib/tiers.ts` defines tier permissions.
- `lib/firebase.ts` contains Firebase client setup.
- `lib/mock.ts` contains safe demo content.
