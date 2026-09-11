#!/usr/bin/env python3
"""Verify the whole system end to end in one command."""
from __future__ import annotations
import json, os, socket, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; SCRATCH=ROOT/"data"/"verify.db"; os.environ["KIVI_DB"]=str(SCRATCH)
PASS,FAIL,WARN="PASS","FAIL","WARN"; results=[]
def check(name,status,detail=""):
    results.append((name,status,detail)); print(f"[{ {PASS:'  ok  ',FAIL:' FAIL ',WARN:' warn '}[status]}] {name}"+(f" — {detail}" if detail else ""))
def main():
    print("Verifying Kivi\n"+"-"*60); v=sys.version_info
    if v>=(3,10):check("Python 3.10 or newer",PASS,f"running {v.major}.{v.minor}.{v.micro}")
    else:check("Python 3.10 or newer",FAIL);return report()
    try:import flask;check("Flask installed",PASS)
    except ImportError:check("Flask installed",FAIL,"run: pip install -r requirements.txt");return report()
    required=["app.py","backend/manage.py","requirements.txt","README.md","docs/RUN.md","web/index.html","resources/corpus/corpus.jsonl","evaluation/run_eval.py","database/migrations/001_initial.sql","docs/POSITION.md","docs/VISION.md","database/migrations/003_shortcuts.sql","backend/kivi/memory/shortcuts.py","extension/manifest.json","extension/content.js","extension/background.js","extension/popup.html","extension/popup.js"]
    missing=[f for f in required if not(ROOT/f).exists()]
    check("All required files present",FAIL if missing else PASS,f"missing: {', '.join(missing)}" if missing else f"{len(required)} checked")
    placeholder=any("REPLACE THIS ENTIRE FILE" in (ROOT/d).read_text(encoding="utf8") or "paste your" in (ROOT/d).read_text(encoding="utf8") for d in ("docs/POSITION.md","docs/VISION.md"))
    check("Position and vision written",FAIL if placeholder else PASS,"docs/ still contains placeholders" if placeholder else "")
    from kivi import db as dbmod
    if SCRATCH.exists():dbmod.reset(SCRATCH)
    conn=dbmod.connect(SCRATCH,auto_migrate=False); applied=dbmod.migrate(conn); tables={r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}; expected={"utterance","memory","memory_event","trace","trace_step","schema_migrations","shortcut_collision"}
    check("Migrations create the schema",PASS if expected<=tables else FAIL,f"{len(applied)} applied, {len(expected)} expected tables")
    check("Migrations are idempotent",PASS if not dbmod.pending(conn) else FAIL,str(dbmod.pending(conn))); conn.close()
    from kivi import corpus_io
    try:records=corpus_io.load(ROOT/"resources"/"corpus"/"corpus.jsonl");age_h=(time.time()-max(r["ts"] for r in records))/3600;check("Corpus loads and rebases",PASS,f"{len(records)} records, newest {age_h:.0f}h old")
    except Exception as e:check("Corpus loads and rebases",FAIL,str(e));return report()
    from kivi.heykivi.run import ask,dictate
    from kivi.memory import shortcuts
    conn=dbmod.connect(SCRATCH); started=time.time()
    for rec in records:dictate(conn,rec);shortcuts.install_from_record(conn,rec)
    counts={k:conn.execute("SELECT COUNT(*) c FROM memory WHERE kind=? AND status IN ('active','observed')",(k,)).fetchone()["c"] for k in ("fact","preference","episode","shortcut")}
    check("Seeding builds memory",PASS if all(counts.values()) else FAIL,f"{counts['fact']} words, {counts['shortcut']} shortcuts, {counts['preference']} rules, {counts['episode']} dictations in {time.time()-started:.1f}s")
    r=ask(conn,"find the dictation I did around 5 PM yesterday in Slack and polish it for the meeting I'm walking into",app="Slack");check("Chained request works",PASS if r.get("status")=="found_and_reshaped" and (r.get("episode") or {}).get("scope_app")=="Slack" else FAIL,f"got {r.get('status')}")
    d=dictate(conn,{"app":"Slack","raw_asr":"Numbers for the Sharvam pilot are in the sheet.","formatted":"Numbers for the Sharvam pilot are in the sheet."});check("Learned spellings apply",PASS if "Sarvam AI" in d["text"] else FAIL,d["text"][:60])
    r=ask(conn,"remember that my portal password is kivi@2026",app="Gmail");check("Sensitive content refused",PASS if r.get("status")=="declined" else FAIL,f"got {r.get('status')}")
    r=ask(conn,"send this to him",app="Gmail");check("Asks instead of guessing",PASS if r.get("status") in ("ambiguous","unclear") else FAIL,f"got {r.get('status')}")
    r=ask(conn,"professorize this",app="Gmail",selection="hey sir sorry to bother you again but i still haven't got the dataset access, can you check when you get time, sorry again");check("Shortcuts fire and rewrite",PASS if r.get("via_shortcut")=="professorize this" and "Dear" in r.get("after","") else FAIL,f"got {r.get('status')}")
    r=ask(conn,"standup-ify",app="Gmail",selection="the numbers are ready");check("Shortcut scope enforced",PASS if r.get("status")=="out_of_scope" else FAIL,f"got {r.get('status')}")
    r=ask(conn,"standup iffy",app="Slack",selection="the numbers are ready");check("Similar triggers ask",PASS if r.get("status")=="ambiguous_trigger" else FAIL,f"got {r.get('status')}")
    before=conn.execute("SELECT COUNT(*) c FROM memory WHERE kind='shortcut'").fetchone()["c"];r=ask(conn,"founder-tone means direct, no hedging, one clear ask",app="Gmail");after=conn.execute("SELECT COUNT(*) c FROM memory WHERE kind='shortcut'").fetchone()["c"];check("Teaching saves nothing yet",PASS if r.get("status")=="shortcut_draft" and after==before else FAIL,f"status {r.get('status')}, stored {after-before}")
    r=ask(conn,"make this shorter",app="Gmail",selection="The implementation requires significant engineering effort.");check("Unknown phrases fall through",PASS if r.get("intent")=="reshape" else FAIL,f"routed as {r.get('intent')}")
    scope=conn.execute("SELECT detail FROM trace_step WHERE stage='memory_scope' AND trace_id IN (SELECT id FROM trace WHERE surface='dictation') ORDER BY id DESC LIMIT 1").fetchone();check("Dictation boundary enforced",PASS if scope and json.loads(scope["detail"]).get("reads")==["fact"] else FAIL)
    traces=conn.execute("SELECT COUNT(*) c FROM trace").fetchone()["c"];steps=conn.execute("SELECT COUNT(*) c FROM trace_step").fetchone()["c"];check("Traces recorded",PASS if traces and steps else FAIL,f"{traces} traces, {steps} steps");conn.close()
    from kivi.api import app as flask_app
    client=flask_app.test_client();s=client.get("/api/status");check("API responds",PASS if s.status_code==200 else FAIL)
    m=client.get("/api/memory");check("Memory surface serves",PASS if m.status_code==200 and "counts" in m.get_json() else FAIL)
    sc=client.get("/api/shortcuts");check("Shortcut surface serves",PASS if sc.status_code==200 and "shortcuts" in sc.get_json() else FAIL)
    page=client.get("/");html=page.data.decode("utf8","replace");markers=["<title>Kivi","/api/ask","/api/dictate","What Kivi knows","Your shortcuts","/api/shortcuts"];found=[x for x in markers if x in html];check("Interface serves",PASS if page.status_code==200 and len(found)==len(markers) else FAIL,f"matched {len(found)}/{len(markers)}")
    try:
        mf=json.loads((ROOT/"extension/manifest.json").read_text());problems=[]
        if mf.get("manifest_version")!=3:problems.append("not manifest v3")
        hosts=" ".join(mf.get("host_permissions",[]))
        if "127.0.0.1:8000" not in hosts:problems.append("backend not in host_permissions")
        scripts=mf.get("content_scripts") or [{}]; first=scripts[0] if scripts else {}; referenced=list(first.get("js",[]))+list(first.get("css",[]))
        if mf.get("background",{}).get("service_worker"):referenced.append(mf["background"]["service_worker"])
        if mf.get("action",{}).get("default_popup"):referenced.append(mf["action"]["default_popup"])
        for f in referenced:
            if f and not(ROOT/"extension"/f).exists():problems.append(f"missing {f}")
        for icon in (mf.get("icons") or {}).values():
            if not(ROOT/"extension"/icon).exists():problems.append(f"missing icon {icon}")
        check("Chrome extension well formed",FAIL if problems else PASS,"; ".join(problems) if problems else "manifest v3, all referenced files present")
    except Exception as e:check("Chrome extension well formed",FAIL,str(e))
    ext_origin="chrome-extension://verifyverifyverifyverifyverifyab";pre=client.open("/api/ask",method="OPTIONS",headers={"Origin":ext_origin});allowed=pre.headers.get("Access-Control-Allow-Origin")==ext_origin;page=client.get("/api/status",headers={"Origin":"https://example.com"});blocked="Access-Control-Allow-Origin" not in page.headers;check("Extension can reach the backend",PASS if allowed and blocked else FAIL)
    port=int(os.environ.get("KIVI_PORT","8000"));sock=socket.socket()
    try:sock.bind(("127.0.0.1",port));check(f"Port {port} is free",PASS)
    except OSError:check(f"Port {port} is free",WARN,"something is already using it")
    finally:sock.close()
    dbmod.reset(SCRATCH);return report()
def report():
    failed=[n for n,s,_ in results if s==FAIL];warned=[n for n,s,_ in results if s==WARN];print("-"*60)
    if failed:
        print(f"{len(failed)} check(s) FAILED:");[print(f"  - {n}") for n in failed];print("\nFix these before submitting.");return 1
    print(f"All checks passed{', '+str(len(warned))+' warning(s)' if warned else ''}. The system runs end to end.");return 0
if __name__=="__main__":sys.exit(main())
