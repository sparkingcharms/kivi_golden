"""Creating, changing and removing memories.

The rules that matter:

  * A memory created from an explicit instruction or an in-place correction is
    active immediately. The person said it; asking again would be rude.
  * A memory inferred from behaviour starts `observed` and is never applied.
    It becomes active only after POLICY["promotion_observations"] independent
    sightings, and the person can see it sitting there in the meantime.
  * Editing never overwrites. The old row is retired and points at the new one,
    so "why did Kivi do that" is answerable months later.
  * A new preference that contradicts an active one does not win by being
    newer. It is held as a conflict for the person to settle.
"""
from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Iterable

from ..config import POLICY
from ..db import jdump, jload, now
from ..llm import Usage, get_backend
from ..local_model import Candidate


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# utterances
# --------------------------------------------------------------------------

def record_utterance(conn: sqlite3.Connection, record: dict[str, Any]) -> str:
    uid = record.get("id") or _id("utt")
    conn.execute(
        """INSERT OR REPLACE INTO utterance
           (id, ts, app, surface, raw_asr, formatted, languages, private, meta)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            uid,
            float(record.get("ts") or now()),
            record.get("app") or "Unknown",
            record.get("surface") or "dictation",
            record.get("raw_asr") or "",
            record.get("formatted") or "",
            jdump(record.get("languages") or ["en"]),
            1 if record.get("private") else 0,
            jdump(record.get("meta") or {}),
        ),
    )
    return uid


# --------------------------------------------------------------------------
# ingestion
# --------------------------------------------------------------------------

def ingest(conn: sqlite3.Connection, record: dict[str, Any], backend=None) -> dict[str, Any]:
    """Run one utterance through extraction and write the result.

    Returns a report describing every decision, which the UI renders directly
    and the evaluation asserts against.
    """
    backend = backend or get_backend()
    usage = Usage(backend=getattr(backend, "name", "local"))

    uid = record_utterance(conn, record)
    result, u = backend.extract(record)
    usage.add(u)

    created: list[dict] = []
    reinforced: list[dict] = []
    conflicts: list[dict] = []
    ignored = list(result.get("ignored", []))

    # An episode happened when it was spoken, not when the row was written.
    # Retrieval filters on that time, so it has to come from the utterance.
    event_ts = float(record.get("ts") or now())

    for raw in result.get("candidates", []):
        cand = raw if isinstance(raw, dict) else raw.as_dict()
        outcome = _upsert(conn, cand, uid, event_ts)
        bucket = {"created": created, "reinforced": reinforced, "conflict": conflicts}.get(outcome["outcome"])
        if bucket is not None:
            bucket.append(outcome)
        else:
            ignored.append({"what": cand.get("body", ""), "reason": outcome.get("reason", "")})

    conn.commit()
    return {
        "utterance_id": uid,
        "created": created,
        "reinforced": reinforced,
        "conflicts": conflicts,
        "ignored": ignored,
        "usage": usage.as_dict(),
    }


def _upsert(conn: sqlite3.Connection, cand: dict[str, Any], utt_id: str | None,
            event_ts: float | None = None) -> dict[str, Any]:
    kind = cand.get("kind")
    subject = (cand.get("subject") or "").strip()
    body = (cand.get("body") or "").strip()
    origin = cand.get("origin") or "observed"
    confidence = float(cand.get("confidence") or 0.0)

    if not subject or not body:
        return {"outcome": "ignored", "reason": "empty candidate"}

    if confidence < POLICY["extract_confidence_floor"] and origin == "taught":
        return {"outcome": "ignored", "reason": f"confidence {confidence:.2f} under the floor"}

    # Episodes are records, not claims. They are never merged or promoted.
    if kind == "episode":
        mid = _insert(conn, cand, utt_id, status="active", event_ts=event_ts)
        return {"outcome": "created", "id": mid, "kind": kind, "body": body,
                "status": "active", "reason": cand.get("reason", "")}

    existing = conn.execute(
        """SELECT * FROM memory
           WHERE kind=? AND subject=? AND status IN ('observed','active')
           ORDER BY created_ts DESC LIMIT 1""",
        (kind, subject),
    ).fetchone()

    if existing:
        obs = existing["observations"] + 1
        status = existing["status"]
        promoted = False
        if status == "observed" and (
            origin in ("taught", "corrected") or obs >= POLICY["promotion_observations"]
        ):
            status = "active"
            promoted = True
        conn.execute(
            """UPDATE memory SET observations=?, status=?, confidence=?, updated_ts=?
               WHERE id=?""",
            (obs, status, max(existing["confidence"], confidence), now(), existing["id"]),
        )
        _event(conn, existing["id"], "promoted" if promoted else "observed",
               f"seen {obs}x" + (" — now active" if promoted else ""), utt_id)
        return {
            "outcome": "reinforced", "id": existing["id"], "kind": kind, "body": existing["body"],
            "status": status, "observations": obs, "promoted": promoted,
            "reason": f"already known; seen {obs} time{'s' if obs != 1 else ''}"
                      + (f", promoted at {POLICY['promotion_observations']}" if promoted else ""),
        }

    # A contradicting active preference is not silently replaced.
    if kind == "preference":
        clash = _find_conflict(conn, cand)
        if clash:
            mid = _insert(conn, cand, utt_id, status="observed", event_ts=event_ts,
                          reason=f"conflicts with an active rule: “{clash['body']}”")
            _event(conn, mid, "observed", f"conflicts with {clash['id']}", utt_id)
            return {"outcome": "conflict", "id": mid, "kind": kind, "body": body,
                    "against": {"id": clash["id"], "body": clash["body"]},
                    "reason": "held for you to settle; the older rule still applies"}

    status = "active" if origin in ("taught", "corrected") else "observed"
    mid = _insert(conn, cand, utt_id, status=status, event_ts=event_ts)
    _event(conn, mid, "promoted" if status == "active" else "observed",
           cand.get("reason", ""), utt_id)
    return {
        "outcome": "created", "id": mid, "kind": kind, "body": body, "status": status,
        "reason": cand.get("reason", ""),
        "needs": None if status == "active"
                 else f"{POLICY['promotion_observations'] - 1} more sightings before it applies",
    }


def _find_conflict(conn: sqlite3.Connection, cand: dict[str, Any]) -> sqlite3.Row | None:
    payload = cand.get("payload") or {}
    # `applies_to` is scope, not content. Two rules about different surfaces
    # cannot contradict each other, and differing scope is never itself a clash.
    keys = [k for k in payload if k not in ("source_text", "unstructured", "applies_to")]
    if not keys:
        return None
    for row in conn.execute(
        "SELECT * FROM memory WHERE kind='preference' AND status='active'"
    ):
        other = jload(row["payload"])
        if other.get("applies_to") != payload.get("applies_to"):
            continue
        for k in keys:
            if k not in other or other[k] == payload[k]:
                continue
            # 0 means "bullets, count unspecified" — it does not contradict a
            # rule that names a count.
            if k == "bullets" and 0 in (other[k], payload[k]):
                continue
            return row
    return None


def _insert(conn: sqlite3.Connection, cand: dict[str, Any], utt_id: str | None,
            status: str, reason: str | None = None, event_ts: float | None = None) -> str:
    mid = _id("mem")
    t = float(event_ts) if event_ts else now()
    conn.execute(
        """INSERT INTO memory
           (id, kind, subject, body, payload, status, confidence, observations,
            scope_app, created_ts, updated_ts, source_utt, origin, reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            mid, cand.get("kind"), cand.get("subject"), cand.get("body"),
            jdump(cand.get("payload") or {}), status, float(cand.get("confidence") or 0.0),
            1, cand.get("scope_app"), t, now(), utt_id,
            cand.get("origin") or "observed", reason or cand.get("reason") or "",
        ),
    )
    return mid


def _event(conn: sqlite3.Connection, memory_id: str, event: str,
           detail: str = "", utt_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO memory_event (memory_id, ts, event, detail, utt_id) VALUES (?,?,?,?,?)",
        (memory_id, now(), event, detail, utt_id),
    )


# --------------------------------------------------------------------------
# person-facing operations
# --------------------------------------------------------------------------

def teach(conn: sqlite3.Connection, kind: str, body: str, payload: dict | None = None,
          subject: str | None = None, scope_app: str | None = None) -> dict:
    from ..local_model import _compile_rule, normalise_key

    payload = payload or (_compile_rule(body) if kind == "preference" else {})
    cand = {
        "kind": kind, "subject": subject or normalise_key(body)[:80], "body": body,
        "payload": payload, "confidence": 0.97, "origin": "taught",
        "reason": "you told Kivi directly", "scope_app": scope_app,
    }
    out = _upsert(conn, cand, utt_id=None)
    conn.commit()
    return out


def edit(conn: sqlite3.Connection, memory_id: str, body: str) -> dict:
    from ..local_model import _compile_rule

    row = conn.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone()
    if not row:
        return {"error": "no such memory"}
    new = _insert(
        conn,
        {
            "kind": row["kind"], "subject": row["subject"], "body": body,
            "payload": _compile_rule(body) if row["kind"] == "preference" else jload(row["payload"]),
            "confidence": row["confidence"], "origin": "taught",
            "reason": "edited by you", "scope_app": row["scope_app"],
        },
        row["source_utt"], status="active",
    )
    conn.execute("UPDATE memory SET status='retired', superseded_by=?, updated_ts=? WHERE id=?",
                 (new, now(), memory_id))
    _event(conn, memory_id, "edited", f"superseded by {new}")
    _event(conn, new, "promoted", f"replaces {memory_id}")
    conn.commit()
    return {"id": new, "replaces": memory_id, "body": body}


def retire(conn: sqlite3.Connection, memory_id: str, reason: str = "you removed it") -> dict:
    conn.execute("UPDATE memory SET status='retired', updated_ts=? WHERE id=?", (now(), memory_id))
    _event(conn, memory_id, "retired", reason)
    conn.commit()
    return {"id": memory_id, "status": "retired", "reason": reason}


def promote(conn: sqlite3.Connection, memory_id: str) -> dict:
    conn.execute("UPDATE memory SET status='active', updated_ts=? WHERE id=?", (now(), memory_id))
    _event(conn, memory_id, "promoted", "confirmed by you")
    conn.commit()
    return {"id": memory_id, "status": "active"}


def reject(conn: sqlite3.Connection, memory_id: str) -> dict:
    conn.execute("UPDATE memory SET status='rejected', updated_ts=? WHERE id=?", (now(), memory_id))
    _event(conn, memory_id, "rejected", "you said it was not a rule")
    conn.commit()
    return {"id": memory_id, "status": "rejected"}


def mark_used(conn: sqlite3.Connection, ids: Iterable[str], trace_id: str) -> None:
    t = now()
    for mid in ids:
        conn.execute(
            "UPDATE memory SET use_count=use_count+1, last_used_ts=? WHERE id=?", (t, mid)
        )
        _event(conn, mid, "applied", f"trace {trace_id}")
    conn.commit()


def history(conn: sqlite3.Connection, memory_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM memory_event WHERE memory_id=? ORDER BY ts", (memory_id,)
    ).fetchall()
    return [dict(r) for r in rows]
