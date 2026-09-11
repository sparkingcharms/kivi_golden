"""Traces.

One trace per request. Every stage appends a step. Nothing that influences an
answer is allowed to stay implicit — if a memory was retrieved, applied,
skipped or missed, there is a step saying so with the numbers attached.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from .db import jdump, jload
from .llm import Usage


class Trace:
    def __init__(self, conn: sqlite3.Connection, surface: str, request: str,
                 app: str | None = None) -> None:
        self.conn = conn
        self.id = f"tr_{uuid.uuid4().hex[:12]}"
        self.surface = surface
        self.request = request
        self.app = app
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []
        self.intent: str | None = None
        self.intent_conf: float = 0.0
        self.outcome: str = "none"
        self.usage = Usage()

    def step(self, stage: str, **detail: Any) -> None:
        self.steps.append({"seq": len(self.steps), "stage": stage, "detail": detail})

    def add_usage(self, usage: Usage) -> None:
        self.usage.add(usage)

    def finish(self, outcome: str) -> dict[str, Any]:
        self.outcome = outcome
        latency = (time.time() - self.started) * 1000.0
        self.conn.execute(
            """INSERT INTO trace
               (id, ts, surface, request, app, intent, intent_conf, outcome,
                latency_ms, model_calls, input_tokens, output_tokens, cost_usd)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.id, self.started, self.surface, self.request, self.app,
             self.intent, self.intent_conf, outcome, latency, self.usage.calls,
             self.usage.input_tokens, self.usage.output_tokens, self.usage.cost_usd),
        )
        for s in self.steps:
            self.conn.execute(
                "INSERT INTO trace_step (trace_id, seq, stage, detail) VALUES (?,?,?,?)",
                (self.id, s["seq"], s["stage"], jdump(s["detail"])),
            )
        self.conn.commit()
        return {
            "id": self.id, "latency_ms": round(latency, 2), "outcome": outcome,
            "intent": self.intent, "intent_confidence": self.intent_conf,
            "usage": self.usage.as_dict(), "steps": self.steps,
        }


def load(conn: sqlite3.Connection, trace_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM trace WHERE id=?", (trace_id,)).fetchone()
    if not row:
        return None
    steps = conn.execute(
        "SELECT seq, stage, detail FROM trace_step WHERE trace_id=? ORDER BY seq", (trace_id,)
    ).fetchall()
    out = dict(row)
    out["steps"] = [{"seq": s["seq"], "stage": s["stage"], "detail": jload(s["detail"])} for s in steps]
    return out


def recent(conn: sqlite3.Connection, limit: int = 40) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM trace ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
