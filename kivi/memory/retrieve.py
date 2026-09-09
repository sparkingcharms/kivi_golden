"""Retrieval.

Scoring is deliberately legible. Every returned candidate carries the parts
that produced its score, and candidates that fell below the floor are returned
too (marked) so a near-miss is visible in the trace instead of vanishing.

    score = similarity * recency * app_match  (+ exact-subject bonus for facts)
"""
from __future__ import annotations

import math
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any

from ..config import POLICY
from ..db import jload
from ..local_model import bag, cosine, normalise_key

# --------------------------------------------------------------------------
# time hints — "around 5pm yesterday", "last tuesday", "this morning"
# --------------------------------------------------------------------------

_CLOCK = re.compile(r"\b(?:around\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_DAYNAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_PART_OF_DAY = {
    "morning": (6, 12), "afternoon": (12, 17), "evening": (17, 21), "night": (21, 24),
}


def parse_time_hint(text: str, ref: float | None = None) -> dict[str, Any] | None:
    """Turn a spoken time reference into a window. Returns None if absent."""
    if not text:
        return None
    ref_dt = datetime.fromtimestamp(ref or time.time())
    t = text.lower()
    day = None
    label = None

    if "yesterday" in t:
        day, label = ref_dt.date() - timedelta(days=1), "yesterday"
    elif "today" in t or "this morning" in t or "this afternoon" in t or "this evening" in t:
        day, label = ref_dt.date(), "today"
    else:
        m = re.search(r"\b(?:last|on)\s+(" + "|".join(_DAYNAMES) + r")\b", t)
        if m:
            target = _DAYNAMES.index(m.group(1))
            delta = (ref_dt.weekday() - target) % 7 or 7
            day, label = ref_dt.date() - timedelta(days=delta), f"last {m.group(1)}"
        elif re.search(r"\blast week\b", t):
            start = ref_dt - timedelta(days=7)
            return {"start": start.timestamp() - 3 * 86400, "end": start.timestamp() + 4 * 86400,
                    "label": "last week", "tolerance_h": 84}

    if day is None:
        return None

    start_h, end_h = 0, 24
    tolerance = 12.0
    cm = _CLOCK.search(t)
    if cm:
        hour = int(cm.group(1)) % 12
        if cm.group(3).lower() == "pm":
            hour += 12
        centre = datetime.combine(day, datetime.min.time()) + timedelta(
            hours=hour, minutes=int(cm.group(2) or 0)
        )
        window = 1.5 if "around" in t or "about" in t else 0.75
        return {"start": (centre - timedelta(hours=window)).timestamp(),
                "end": (centre + timedelta(hours=window)).timestamp(),
                "label": f"{label} around {cm.group(0).replace('around ', '')}",
                "tolerance_h": window}
    for word, (a, b) in _PART_OF_DAY.items():
        if word in t:
            start_h, end_h, tolerance, label = a, b, (b - a) / 2, f"{label} {word}"
            break

    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=start_h)
    end = datetime.combine(day, datetime.min.time()) + timedelta(hours=end_h)
    return {"start": start.timestamp(), "end": end.timestamp(),
            "label": label, "tolerance_h": tolerance}


KNOWN_APPS = ["slack", "gmail", "whatsapp", "cursor", "notion", "vs code", "docs", "chrome", "teams"]

# Words that only locate a request in time or place. What remains after these
# are removed is the part of the query that is actually about content.
_REFERENCE_WORDS = {
    "find", "show", "pull", "up", "what", "did", "say", "said", "dictate",
    "dictated", "dictation", "spoke", "wrote", "note", "message", "thing",
    "around", "about", "yesterday", "today", "morning", "afternoon", "evening",
    "night", "last", "week", "the", "in", "on", "from", "my", "me", "and",
    "then", "polish", "it", "for", "meeting", "walking", "into", *KNOWN_APPS,
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "am", "pm",
}


def parse_app_hint(text: str) -> str | None:
    t = (text or "").lower()
    for app in KNOWN_APPS:
        if re.search(r"\b(?:in|on|from)\s+" + re.escape(app) + r"\b", t):
            return app
    for app in KNOWN_APPS:
        if app in t:
            return app
    return None


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def _recency(ts: float, ref: float, kind: str) -> float:
    """Episodes decay. Facts and preferences do not — a spelling you fixed in
    March is still your spelling in September."""
    if kind != "episode":
        return 1.0
    age_h = max(0.0, (ref - ts) / 3600.0)
    return 0.5 ** (age_h / POLICY["episode_half_life_hours"])


def search(
    conn: sqlite3.Connection,
    query: str,
    kinds: tuple[str, ...] = ("fact", "preference", "episode"),
    app: str | None = None,
    window: dict[str, Any] | None = None,
    top_k: int | None = None,
    include_observed: bool = False,
    ref_ts: float | None = None,
) -> dict[str, Any]:
    """Return ranked memories plus everything needed to explain the ranking."""
    ref = ref_ts or time.time()
    top_k = top_k or POLICY["retrieval_top_k"]
    qvec = bag(query)
    qkey = normalise_key(query)

    # "what did I say in WhatsApp yesterday evening" carries no content words
    # once the time and app are stripped out — the filters *are* the query.
    # Scoring such a request on word overlap would return nothing, so episodes
    # that satisfy the filters get a baseline relevance instead.
    residual = [t for t in qvec if t not in _REFERENCE_WORDS and (not app or t not in app.lower())]
    filter_driven = bool((window or app)) and len(residual) < 2

    statuses = ("active", "observed") if include_observed else ("active",)
    placeholders_k = ",".join("?" * len(kinds))
    placeholders_s = ",".join("?" * len(statuses))
    rows = conn.execute(
        f"""SELECT * FROM memory
            WHERE kind IN ({placeholders_k}) AND status IN ({placeholders_s})""",
        (*kinds, *statuses),
    ).fetchall()

    scored: list[dict[str, Any]] = []
    for row in rows:
        text = f"{row['subject']} {row['body']}"
        sim = cosine(qvec, bag(text))

        # A fact whose subject appears verbatim in the query is a direct hit,
        # regardless of how short the query is.
        exact = 0.0
        if row["kind"] == "fact" and row["subject"] and row["subject"] in qkey:
            exact = 0.6
        sim = min(1.0, sim + exact)

        baseline = 0.0
        if filter_driven and row["kind"] == "episode":
            baseline = 0.5
            sim = max(sim, baseline)

        rec = _recency(row["created_ts"], ref, row["kind"])

        app_factor = 1.0
        app_note = "no app filter"
        if app and row["kind"] == "episode":
            if (row["scope_app"] or "").lower() == app.lower():
                app_factor, app_note = 1.35, f"in {row['scope_app']}"
            else:
                app_factor, app_note = 0.15, f"not in {app}"

        in_window = True
        window_note = "no time filter"
        if window and row["kind"] == "episode":
            in_window = window["start"] <= row["created_ts"] <= window["end"]
            window_note = window["label"] + (" ✓" if in_window else " ✗")
            if not in_window:
                app_factor *= 0.1

        score = sim * rec * app_factor
        scored.append({
            "id": row["id"], "kind": row["kind"], "body": row["body"],
            "subject": row["subject"], "status": row["status"],
            "payload": jload(row["payload"]), "scope_app": row["scope_app"],
            "created_ts": row["created_ts"], "source_utt": row["source_utt"],
            "score": round(score, 4),
            "why": {
                "similarity": round(sim, 4),
                "exact_subject_bonus": exact,
                "filter_driven_baseline": baseline,
                "recency": round(rec, 4),
                "app": app_note, "app_factor": app_factor,
                "time": window_note,
            },
        })

    scored.sort(key=lambda c: c["score"], reverse=True)
    floor = POLICY["retrieval_floor"]
    hits = [c for c in scored if c["score"] >= floor][:top_k]
    near = [c for c in scored if c["score"] < floor][:5]
    return {
        "hits": hits,
        "below_floor": near,
        "floor": floor,
        "considered": len(scored),
        "filters": {"kinds": list(kinds), "app": app, "window": window,
                    "filter_driven": filter_driven},
    }


def active_rules(conn: sqlite3.Connection, app: str | None = None) -> list[dict[str, Any]]:
    """Every preference currently in force, for reshaping."""
    rows = conn.execute(
        "SELECT * FROM memory WHERE kind='preference' AND status='active' ORDER BY updated_ts DESC"
    ).fetchall()
    out = []
    for r in rows:
        if r["scope_app"] and app and r["scope_app"].lower() != app.lower():
            continue
        payload = jload(r["payload"])
        # A rule that names its own surface only applies on that surface.
        target = payload.get("applies_to")
        if target and app and target.lower() != app.lower():
            continue
        payload["source_text"] = r["body"]
        out.append({"id": r["id"], "body": r["body"], "payload": payload})
    return out


def dictionary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Active facts — the only memory ordinary dictation is allowed to read."""
    rows = conn.execute(
        "SELECT * FROM memory WHERE kind='fact' AND status='active' ORDER BY updated_ts DESC"
    ).fetchall()
    out = []
    for r in rows:
        p = jload(r["payload"])
        if p.get("wrong") and p.get("right"):
            out.append({"id": r["id"], "wrong": p["wrong"], "right": p["right"], "body": r["body"]})
    return out


def apply_dictionary(text: str, entries: list[dict[str, Any]]) -> tuple[str, list[dict]]:
    """Substitute known spellings. This is the whole of memory's effect on
    ordinary dictation: replacing a word Kivi previously heard wrong."""
    used: list[dict] = []
    out = text or ""
    for e in entries:
        pattern = re.compile(rf"\b{re.escape(e['wrong'])}\b", re.I)
        if pattern.search(out):
            out = pattern.sub(e["right"], out)
            used.append(e)
    return out, used
