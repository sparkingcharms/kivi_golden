"""HTTP surface.

Two product endpoints (`/api/dictate`, `/api/ask`), a memory surface the person
uses to see and change what Kivi knows, and a trace endpoint for an engineer.
The UI is served from the same process so there is one thing to run.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import corpus_io
from . import trace as trace_mod
from .config import CORPUS_PATH, DB_PATH, POLICY
from .db import connect, db_size_bytes, jload
from .heykivi.run import ask, dictate
from .llm import get_backend
from .memory import retrieve, store

WEB = Path(__file__).resolve().parent.parent / "web"

app = Flask(__name__, static_folder=None)


def db():
    return connect()


# --------------------------------------------------------------------------
# product
# --------------------------------------------------------------------------

@app.post("/api/dictate")
def api_dictate():
    payload = request.get_json(force=True) or {}
    conn = db()
    try:
        return jsonify(dictate(conn, {
            "app": payload.get("app", "Slack"),
            "raw_asr": payload.get("text", ""),
            "formatted": payload.get("formatted") or payload.get("text", ""),
            "languages": payload.get("languages") or ["en"],
            "private": bool(payload.get("private")),
            "meta": payload.get("meta") or {},
        }))
    finally:
        conn.close()


@app.post("/api/ask")
def api_ask():
    payload = request.get_json(force=True) or {}
    conn = db()
    try:
        return jsonify(ask(
            conn,
            payload.get("text", ""),
            app=payload.get("app"),
            selection=payload.get("selection"),
            backend=get_backend(),
        ))
    finally:
        conn.close()


# --------------------------------------------------------------------------
# the memory surface
# --------------------------------------------------------------------------

@app.get("/api/memory")
def api_memory():
    conn = db()
    try:
        rows = conn.execute(
            """SELECT * FROM memory WHERE status IN ('active','observed')
               ORDER BY kind, updated_ts DESC"""
        ).fetchall()
        out = {"fact": [], "preference": [], "episode": []}
        for r in rows:
            if r["kind"] == "episode":
                continue
            out[r["kind"]].append({
                "id": r["id"], "body": r["body"], "status": r["status"],
                "origin": r["origin"], "reason": r["reason"],
                "observations": r["observations"], "use_count": r["use_count"],
                "scope_app": r["scope_app"], "payload": jload(r["payload"]),
                "created_ts": r["created_ts"], "source_utt": r["source_utt"],
                "needs": None if r["status"] == "active"
                         else max(0, POLICY["promotion_observations"] - r["observations"]),
            })
        episodes = conn.execute(
            """SELECT * FROM memory WHERE kind='episode' AND status='active'
               ORDER BY created_ts DESC LIMIT 25"""
        ).fetchall()
        out["episode"] = [{
            "id": r["id"], "body": r["body"], "app": r["scope_app"],
            "created_ts": r["created_ts"], "source_utt": r["source_utt"],
        } for r in episodes]
        counts = {
            "facts": len(out["fact"]),
            "rules_active": sum(1 for p in out["preference"] if p["status"] == "active"),
            "rules_observed": sum(1 for p in out["preference"] if p["status"] == "observed"),
            "episodes": conn.execute(
                "SELECT COUNT(*) c FROM memory WHERE kind='episode' AND status='active'"
            ).fetchone()["c"],
            "db_bytes": db_size_bytes(DB_PATH),
        }
        return jsonify({"memory": out, "counts": counts, "policy": {
            "promotion_observations": POLICY["promotion_observations"],
            "dictation_reads": list(POLICY["dictation_reads"]),
            "heykivi_reads": list(POLICY["heykivi_reads"]),
            "never_learn": list(POLICY["never_learn"]),
        }})
    finally:
        conn.close()


@app.post("/api/memory/<mid>/<action>")
def api_memory_action(mid: str, action: str):
    conn = db()
    try:
        if action == "confirm":
            return jsonify(store.promote(conn, mid))
        if action == "reject":
            return jsonify(store.reject(conn, mid))
        if action == "forget":
            return jsonify(store.retire(conn, mid))
        if action == "edit":
            body = (request.get_json(force=True) or {}).get("body", "")
            return jsonify(store.edit(conn, mid, body))
        return jsonify({"error": f"unknown action {action}"}), 400
    finally:
        conn.close()


@app.get("/api/memory/<mid>/history")
def api_memory_history(mid: str):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM memory WHERE id=?", (mid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        src = None
        if row["source_utt"]:
            u = conn.execute("SELECT * FROM utterance WHERE id=?", (row["source_utt"],)).fetchone()
            if u:
                src = {"id": u["id"], "ts": u["ts"], "app": u["app"], "raw_asr": u["raw_asr"]}
        return jsonify({
            "memory": {"id": row["id"], "kind": row["kind"], "body": row["body"],
                       "status": row["status"], "origin": row["origin"],
                       "reason": row["reason"], "observations": row["observations"],
                       "use_count": row["use_count"], "superseded_by": row["superseded_by"]},
            "source": src,
            "events": store.history(conn, mid),
        })
    finally:
        conn.close()


@app.post("/api/teach")
def api_teach():
    payload = request.get_json(force=True) or {}
    conn = db()
    try:
        return jsonify(store.teach(conn, payload.get("kind", "preference"),
                                   payload.get("body", "")))
    finally:
        conn.close()


# --------------------------------------------------------------------------
# engineer surface
# --------------------------------------------------------------------------

@app.get("/api/trace/<tid>")
def api_trace(tid: str):
    conn = db()
    try:
        t = trace_mod.load(conn, tid)
        return (jsonify(t), 200) if t else (jsonify({"error": "not found"}), 404)
    finally:
        conn.close()


@app.get("/api/traces")
def api_traces():
    conn = db()
    try:
        return jsonify({"traces": trace_mod.recent(conn, int(request.args.get("n", 30)))})
    finally:
        conn.close()


@app.post("/api/seed")
def api_seed():
    """Load the corpus. Idempotent — running it twice does not double the store."""
    conn = db()
    try:
        existing = conn.execute("SELECT COUNT(*) c FROM utterance").fetchone()["c"]
        if existing:
            return jsonify({"status": "already seeded", "utterances": existing})
        n = 0
        for rec in corpus_io.load(CORPUS_PATH):
            dictate(conn, rec)
            n += 1
        return jsonify({"status": "seeded", "utterances": n})
    finally:
        conn.close()


@app.get("/api/status")
def api_status():
    conn = db()
    try:
        return jsonify({
            "backend": getattr(get_backend(), "name", "local"),
            "utterances": conn.execute("SELECT COUNT(*) c FROM utterance").fetchone()["c"],
            "memories": conn.execute(
                "SELECT COUNT(*) c FROM memory WHERE status IN ('active','observed')"
            ).fetchone()["c"],
            "db_bytes": db_size_bytes(DB_PATH),
        })
    finally:
        conn.close()


# --------------------------------------------------------------------------
# static
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    return send_from_directory(WEB, path)
