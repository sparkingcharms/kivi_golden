"""HTTP surface."""
from __future__ import annotations
import json
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from . import corpus_io, trace as trace_mod
from .config import CORPUS_PATH, DB_PATH, POLICY
from .db import connect, db_size_bytes, jload
from .heykivi.run import ask, dictate
from .llm import get_backend
from .memory import retrieve, shortcuts, store
WEB = Path(__file__).resolve().parents[2] / "web"
app = Flask(__name__, static_folder=None)
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")
@app.after_request
def cors(response):
    origin=request.headers.get("Origin","")
    if origin.startswith(ALLOWED_ORIGIN_PREFIXES):
        response.headers["Access-Control-Allow-Origin"]=origin; response.headers["Access-Control-Allow-Headers"]="Content-Type"; response.headers["Access-Control-Allow-Methods"]="GET, POST, OPTIONS"; response.headers["Vary"]="Origin"
    return response
@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any): return ("",204)
def db(): return connect()
@app.post("/api/dictate")
def api_dictate():
    p=request.get_json(force=True) or {}; conn=db()
    try: return jsonify(dictate(conn,{"app":p.get("app","Slack"),"raw_asr":p.get("text",""),"formatted":p.get("formatted") or p.get("text",""),"languages":p.get("languages") or ["en"],"private":bool(p.get("private")),"meta":p.get("meta") or {}}))
    finally: conn.close()
@app.post("/api/ask")
def api_ask():
    p=request.get_json(force=True) or {}; conn=db()
    try: return jsonify(ask(conn,p.get("text",""),app=p.get("app"),selection=p.get("selection"),backend=get_backend()))
    finally: conn.close()
@app.get("/api/memory")
def api_memory():
    conn=db()
    try:
        rows=conn.execute("SELECT * FROM memory WHERE status IN ('active','observed') ORDER BY kind,updated_ts DESC").fetchall(); out={"fact":[],"preference":[],"episode":[],"shortcut":[]}
        for r in rows:
            if r["kind"]=="episode": continue
            if r["kind"]=="shortcut":
                p=jload(r["payload"]); out["shortcut"].append({"id":r["id"],"phrase":p.get("phrase",r["subject"]),"body":r["body"],"understood":p.get("understood",[]),"apps":p.get("apps",[]),"fires_on":p.get("fires_on","selection"),"use_count":r["use_count"],"status":r["status"],"not_executable":p.get("not_executable",[])}); continue
            out[r["kind"]].append({"id":r["id"],"body":r["body"],"status":r["status"],"origin":r["origin"],"reason":r["reason"],"observations":r["observations"],"use_count":r["use_count"],"scope_app":r["scope_app"],"payload":jload(r["payload"]),"created_ts":r["created_ts"],"source_utt":r["source_utt"],"needs":None if r["status"]=="active" else max(0,POLICY["promotion_observations"]-r["observations"])})
        episodes=conn.execute("SELECT * FROM memory WHERE kind='episode' AND status='active' ORDER BY created_ts DESC LIMIT 25").fetchall(); out["episode"]=[{"id":r["id"],"body":r["body"],"app":r["scope_app"],"created_ts":r["created_ts"],"source_utt":r["source_utt"]} for r in episodes]
        counts={"shortcuts":conn.execute("SELECT COUNT(*) c FROM memory WHERE kind='shortcut' AND status='active'").fetchone()["c"],"facts":len(out["fact"]),"rules_active":sum(1 for p in out["preference"] if p["status"]=="active"),"rules_observed":sum(1 for p in out["preference"] if p["status"]=="observed"),"episodes":conn.execute("SELECT COUNT(*) c FROM memory WHERE kind='episode' AND status='active'").fetchone()["c"],"db_bytes":db_size_bytes(DB_PATH)}
        return jsonify({"memory":out,"counts":counts,"policy":{"promotion_observations":POLICY["promotion_observations"],"dictation_reads":list(POLICY["dictation_reads"]),"heykivi_reads":list(POLICY["heykivi_reads"]),"never_learn":list(POLICY["never_learn"])}})
    finally: conn.close()
@app.post("/api/memory/<mid>/<action>")
def api_memory_action(mid,action):
    conn=db()
    try:
        if action=="confirm": return jsonify(store.promote(conn,mid))
        if action=="reject": return jsonify(store.reject(conn,mid))
        if action=="forget": return jsonify(store.retire(conn,mid))
        if action=="edit": return jsonify(store.edit(conn,mid,(request.get_json(force=True) or {}).get("body","")))
        return jsonify({"error":f"unknown action {action}"}),400
    finally: conn.close()
@app.get("/api/memory/<mid>/history")
def api_memory_history(mid):
    conn=db()
    try:
        row=conn.execute("SELECT * FROM memory WHERE id=?",(mid,)).fetchone()
        if not row:return jsonify({"error":"not found"}),404
        src=None
        if row["source_utt"]:
            u=conn.execute("SELECT * FROM utterance WHERE id=?",(row["source_utt"],)).fetchone()
            if u:src={"id":u["id"],"ts":u["ts"],"app":u["app"],"raw_asr":u["raw_asr"]}
        return jsonify({"memory":{"id":row["id"],"kind":row["kind"],"body":row["body"],"status":row["status"],"origin":row["origin"],"reason":row["reason"],"observations":row["observations"],"use_count":row["use_count"],"superseded_by":row["superseded_by"]},"source":src,"events":store.history(conn,mid)})
    finally: conn.close()
@app.post("/api/teach")
def api_teach():
    p=request.get_json(force=True) or {}; conn=db()
    try:return jsonify(store.teach(conn,p.get("kind","preference"),p.get("body","")))
    finally:conn.close()
@app.get("/api/shortcuts")
def api_shortcuts():
    conn=db()
    try:return jsonify({"shortcuts":shortcuts.listing(conn),"collisions":shortcuts.collisions(conn)})
    finally:conn.close()
@app.post("/api/shortcuts/interpret")
def api_shortcut_interpret():
    p=request.get_json(force=True) or {}; return jsonify(shortcuts.interpret(p.get("phrase",""),p.get("meaning",""),apps=p.get("apps") or [],fires_on=p.get("fires_on","selection"),examples=p.get("examples") or []))
@app.post("/api/shortcuts/save")
def api_shortcut_save():
    p=request.get_json(force=True) or {}; draft=p.get("draft") or shortcuts.interpret(p.get("phrase",""),p.get("meaning",""),apps=p.get("apps") or [],fires_on=p.get("fires_on","selection")); conn=db()
    try:return jsonify(shortcuts.save(conn,draft))
    finally:conn.close()
@app.post("/api/shortcuts/<mid>/rename")
def api_shortcut_rename(mid):
    p=request.get_json(force=True) or {}; conn=db()
    try:return jsonify(shortcuts.rename(conn,mid,p.get("phrase","")))
    finally:conn.close()
@app.get("/api/trace/<tid>")
def api_trace(tid):
    conn=db()
    try:
        t=trace_mod.load(conn,tid); return (jsonify(t),200) if t else (jsonify({"error":"not found"}),404)
    finally:conn.close()
@app.get("/api/traces")
def api_traces():
    conn=db()
    try:return jsonify({"traces":trace_mod.recent(conn,int(request.args.get("n",30)))})
    finally:conn.close()
@app.post("/api/seed")
def api_seed():
    conn=db()
    try:
        existing=conn.execute("SELECT COUNT(*) c FROM utterance").fetchone()["c"]
        if existing:return jsonify({"status":"already seeded","utterances":existing})
        n=0
        for rec in corpus_io.load(CORPUS_PATH):dictate(conn,rec); shortcuts.install_from_record(conn,rec); n+=1
        return jsonify({"status":"seeded","utterances":n})
    finally:conn.close()
@app.get("/api/status")
def api_status():
    conn=db()
    try:return jsonify({"backend":getattr(get_backend(),"name","local"),"utterances":conn.execute("SELECT COUNT(*) c FROM utterance").fetchone()["c"],"memories":conn.execute("SELECT COUNT(*) c FROM memory WHERE status IN ('active','observed')").fetchone()["c"],"db_bytes":db_size_bytes(DB_PATH)})
    finally:conn.close()
@app.get("/")
def index():return send_from_directory(WEB,"index.html")
@app.get("/<path:path>")
def static_files(path):return send_from_directory(WEB,path)
