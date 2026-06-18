"""
AIMi — Conversion Funnel for chataimi.ai
========================================
Tracks every visitor through the funnel:

  VISITOR → ENGAGED → SIGNUP → ACTIVATED → TRIAL → PAID → ENTERPRISE_LEAD

Design choices that drive conversion:
  • Free tier is generous on education, gated on signals/portfolio depth
  • Value moments (3 AI answers, 1 signal viewed) trigger contextual
    signup / upgrade prompts instead of hard paywalls
  • Lead scoring surfaces enterprise prospects (universities, advisers)
    for the sales pipeline
  • Funnel analytics endpoint feeds the dashboard's conversion chart

Storage is SQLite (zero-config); swap the DSN for Postgres in production.
"""

from __future__ import annotations
import json
import time
import uuid
import sqlite3
import logging
from contextlib import contextmanager
from dataclasses import dataclass

log = logging.getLogger("aimi.funnel")

DB_PATH = "aimi_funnel.db"

STAGES = ["visitor", "engaged", "signup", "activated", "trial", "paid", "enterprise_lead"]
STAGE_RANK = {s: i for i, s in enumerate(STAGES)}

# Events that auto-promote a user to a stage
EVENT_STAGE = {
    "page_view":          "visitor",
    "chat_message":       "engaged",
    "signal_viewed":      "engaged",
    "voice_used":         "engaged",
    "email_submitted":    "signup",
    "account_created":    "signup",
    "portfolio_built":    "activated",
    "backtest_run":       "activated",
    "trial_started":      "trial",
    "subscription_paid":  "paid",
    "enterprise_inquiry": "enterprise_lead",
}

# Lead scoring — which actions signal buying intent
EVENT_SCORE = {
    "page_view": 1, "chat_message": 3, "signal_viewed": 5, "voice_used": 4,
    "email_submitted": 15, "account_created": 15, "portfolio_built": 20,
    "backtest_run": 20, "pricing_viewed": 10, "trial_started": 30,
    "subscription_paid": 60, "enterprise_inquiry": 50,
}

# Contextual nudges shown by the frontend at value moments
NUDGE_RULES = [
    {"when": lambda u: u["stage"] == "engaged" and u["counts"].get("chat_message", 0) >= 3
                       and not u["email"],
     "nudge": {"type": "signup", "headline": "Save your AIMi conversations",
               "body": "Create a free account to keep your chat history, watchlist "
                       "and one personalised portfolio.", "cta": "Create free account"}},
    {"when": lambda u: u["counts"].get("signal_viewed", 0) >= 2 and u["stage"] in ("engaged", "signup"),
     "nudge": {"type": "trial", "headline": "Unlock all live signals",
               "body": "You've seen what one signal can do. Pro unlocks the full scanner, "
                       "real-time alerts and institutional risk reports — free for 7 days.",
               "cta": "Start free trial"}},
    {"when": lambda u: u["counts"].get("backtest_run", 0) >= 2 and u["stage"] in ("activated", "trial"),
     "nudge": {"type": "upgrade", "headline": "Backtest without limits",
               "body": "Pro removes the 1-year history cap and adds multi-strategy "
                       "comparison and portfolio-level backtests.", "cta": "Go Pro"}},
    {"when": lambda u: u["counts"].get("enterprise_page", 0) >= 1,
     "nudge": {"type": "enterprise", "headline": "AIMi for your institution",
               "body": "White-label the platform for your university or advisory firm. "
                       "Book a 20-minute demo with our team.", "cta": "Book a demo"}},
]


@contextmanager
def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _init():
    with _db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT, stage TEXT DEFAULT 'visitor',
            score INTEGER DEFAULT 0, source TEXT, created REAL, updated REAL,
            counts TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, event TEXT,
            props TEXT, ts REAL
        );
        CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        """)

_init()


@dataclass
class FunnelTracker:

    # ------------------------------------------------------------- tracking
    def track(self, user_id: str | None, event: str, props: dict | None = None,
              source: str | None = None) -> dict:
        """Record an event; returns user state + any contextual nudge."""
        user_id = user_id or str(uuid.uuid4())
        now = time.time()
        props = props or {}

        with _db() as con:
            row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                con.execute("INSERT INTO users (id, source, created, updated) VALUES (?,?,?,?)",
                            (user_id, source or props.get("utm_source", "direct"), now, now))
                row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

            counts = json.loads(row["counts"])
            counts[event] = counts.get(event, 0) + 1

            stage = row["stage"]
            new_stage = EVENT_STAGE.get(event)
            if new_stage and STAGE_RANK[new_stage] > STAGE_RANK.get(stage, 0):
                stage = new_stage

            email = props.get("email") or row["email"]
            score = row["score"] + EVENT_SCORE.get(event, 0)

            con.execute("""UPDATE users SET stage=?, score=?, email=?, updated=?, counts=?
                           WHERE id=?""",
                        (stage, score, email, now, json.dumps(counts), user_id))
            con.execute("INSERT INTO events (user_id, event, props, ts) VALUES (?,?,?,?)",
                        (user_id, event, json.dumps(props), now))

        state = {"user_id": user_id, "stage": stage, "score": score,
                 "email": email, "counts": counts}
        state["nudge"] = self._nudge(state)
        return state

    @staticmethod
    def _nudge(user: dict) -> dict | None:
        for rule in NUDGE_RULES:
            try:
                if rule["when"](user):
                    return rule["nudge"]
            except Exception:
                continue
        return None

    # ------------------------------------------------------------ analytics
    def funnel_report(self, since_hours: float = 24 * 30) -> dict:
        cutoff = time.time() - since_hours * 3600
        with _db() as con:
            rows = con.execute(
                "SELECT stage, COUNT(*) n FROM users WHERE updated>=? GROUP BY stage",
                (cutoff,)).fetchall()
            by_stage = {r["stage"]: r["n"] for r in rows}
            total = sum(by_stage.values()) or 1

            # users at stage X have passed through all earlier stages
            cumulative = []
            for i, s in enumerate(STAGES):
                reached = sum(n for st, n in by_stage.items()
                              if STAGE_RANK.get(st, 0) >= i)
                cumulative.append({"stage": s, "users": reached,
                                   "pct_of_visitors": round(reached / max(cumulative[0]["users"], 1) * 100, 1)
                                   if cumulative else 100.0})

            top_leads = [dict(r) for r in con.execute(
                """SELECT id, email, stage, score FROM users
                   WHERE score >= 40 AND stage != 'paid'
                   ORDER BY score DESC LIMIT 20""").fetchall()]

            sources = [dict(r) for r in con.execute(
                """SELECT source, COUNT(*) visitors,
                          SUM(CASE WHEN stage IN ('paid','trial') THEN 1 ELSE 0 END) converting
                   FROM users WHERE updated>=? GROUP BY source ORDER BY visitors DESC""",
                (cutoff,)).fetchall()]

        conv = {}
        for a, b in zip(cumulative, cumulative[1:]):
            conv[f"{a['stage']}→{b['stage']}"] = round(
                b["users"] / max(a["users"], 1) * 100, 1)

        return {"window_hours": since_hours, "total_users": total,
                "funnel": cumulative, "stage_conversion_pct": conv,
                "top_leads": top_leads, "sources": sources}


funnel = FunnelTracker()
