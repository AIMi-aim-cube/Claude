# Implementation Notes

## Suggested backend services
- Auth: Firebase Authentication or Clerk
- Database: Firestore / Supabase / Postgres
- Storage: Google Cloud Storage
- AI: Vertex AI Gemini, OpenAI, Anthropic, or hybrid routing
- RAG: Vertex AI Vector Search / Pinecone / Weaviate
- Payments: Stripe subscriptions
- Broker handoff: redirect-only links + referral tracking

## Core collections / tables
- users
- tiers
- subscriptions
- onboarding_profiles
- chat_sessions
- chat_messages
- lessons
- lesson_progress
- insights
- signals
- broker_referrals
- audit_logs
- admin_actions

## Signal object fields
- asset
- strategy
- regime
- directional_bias
- confidence_score
- risk_classification
- time_horizon
- portfolio_impact
- evidence_bundle
- invalidation_conditions
- approval_status
- publish_timestamp

## Compliance guardrails
- No execution inside AIMi
- No personalised advice language
- Mandatory broker exit confirmation
- Tier-based visibility
- Human approval for published premium signals
- Full audit logs for model outputs, prompts, tier changes and signal approvals
