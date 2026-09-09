#!/usr/bin/env python3
"""Verify the whole system, end to end, in one command.

    python verify.py

Checks the runtime, the dependencies, the migrations, the seed, the backend
behaviour, the HTTP layer, and the interface — then prints a pass/fail line for
each and exits non-zero if anything failed.

It works on a scratch database (`data/verify.db`) and never touches the one the
app uses, so it is safe to run at any time, including right before submitting.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Point everything at a scratch database before importing the app.
SCRATCH = ROOT / "data" / "verify.db"
os.environ["KIVI_DB"] = str(SCRATCH)

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def check(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {PASS: "  ok  ", FAIL: " FAIL ", WARN: " warn "}[status]
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("Verifying Kivi\n" + "-" * 60)

    # 1. runtime -----------------------------------------------------------
    v = sys.version_info
    if v >= (3, 10):
        check("Python 3.10 or newer", PASS, f"running {v.major}.{v.minor}.{v.micro}")
    else:
        check("Python 3.10 or newer", FAIL, f"found {v.major}.{v.minor}, upgrade required")
        return report()

    # 2. dependencies ------------------------------------------------------
    try:
        import flask  # noqa: F401
        check("Flask installed", PASS)
    except ImportError:
        check("Flask installed", FAIL, "run: pip install -r requirements.txt")
        return report()

    # 3. project files -----------------------------------------------------
    required = [
        "run.py", "manage.py", "requirements.txt", "README.md", "RUN.md",
        "web/index.html", "corpus/corpus.jsonl", "evaluation/run_eval.py",
        "migrations/001_initial.sql", "docs/POSITION.md", "docs/VISION.md",
    ]
    missing = [f for f in required if not (ROOT / f).exists()]
    if missing:
        check("All required files present", FAIL, f"missing: {', '.join(missing)}")
    else:
        check("All required files present", PASS, f"{len(required)} checked")

    # 4. Part One documents actually written -------------------------------
    placeholder = False
    for doc in ("docs/POSITION.md", "docs/VISION.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        if "REPLACE THIS ENTIRE FILE" in text or "paste your" in text:
            placeholder = True
    if placeholder:
        check("Position and vision written", FAIL,
              "docs/ still contains placeholders — write these before submitting")
    else:
        check("Position and vision written", PASS)

    # 5. migrations --------------------------------------------------------
    from kivi import db as dbmod
    if SCRATCH.exists():
        dbmod.reset(SCRATCH)
    conn = dbmod.connect(SCRATCH, auto_migrate=False)
    applied = dbmod.migrate(conn)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"utterance", "memory", "memory_event", "trace", "trace_step",
                "schema_migrations"}
    if expected <= tables:
        check("Migrations create the schema", PASS,
              f"{len(applied)} applied, {len(expected)} tables")
    else:
        check("Migrations create the schema", FAIL, f"missing {expected - tables}")

    if not dbmod.pending(conn):
        check("Migrations are idempotent", PASS, "nothing pending on re-run")
    else:
        check("Migrations are idempotent", FAIL, str(dbmod.pending(conn)))
    conn.close()

    # 6. corpus ------------------------------------------------------------
    from kivi import corpus_io
    try:
        records = corpus_io.load(ROOT / "corpus" / "corpus.jsonl")
        newest = max(r["ts"] for r in records)
        age_h = (time.time() - newest) / 3600
        check("Corpus loads and rebases", PASS,
              f"{len(records)} records, newest {age_h:.0f}h old")
    except (json.JSONDecodeError, ValueError) as e:
        check("Corpus loads and rebases", FAIL, str(e))
        return report()

    # 7. seed through the real ingestion path ------------------------------
    from kivi.heykivi.run import ask, dictate
    conn = dbmod.connect(SCRATCH)
    started = time.time()
    for rec in records:
        dictate(conn, rec)
    seed_s = time.time() - started
    counts = {k: conn.execute(
        "SELECT COUNT(*) c FROM memory WHERE kind=? AND status IN ('active','observed')",
        (k,)).fetchone()["c"] for k in ("fact", "preference", "episode")}
    if counts["fact"] and counts["preference"] and counts["episode"]:
        check("Seeding builds memory", PASS,
              f"{counts['fact']} words, {counts['preference']} rules, "
              f"{counts['episode']} dictations in {seed_s:.1f}s")
    else:
        check("Seeding builds memory", FAIL, str(counts))

    # 8. backend behaviour -------------------------------------------------
    r = ask(conn, "find the dictation I did around 5 PM yesterday in Slack and "
                  "polish it for the meeting I'm walking into", app="Slack")
    if r.get("status") == "found_and_reshaped" and (r.get("episode") or {}).get("scope_app") == "Slack":
        check("Chained request works", PASS, "found the Slack entry and rewrote it")
    else:
        check("Chained request works", FAIL, f"got {r.get('status')}")

    d = dictate(conn, {"app": "Slack", "raw_asr": "Numbers for the Sharvam pilot are in the sheet.",
                       "formatted": "Numbers for the Sharvam pilot are in the sheet."})
    if "Sarvam AI" in d["text"]:
        check("Learned spellings apply", PASS, "Sharvam corrected in place")
    else:
        check("Learned spellings apply", FAIL, d["text"][:60])

    r = ask(conn, "remember that my portal password is kivi@2026", app="Gmail")
    if r.get("status") == "declined":
        check("Sensitive content refused", PASS)
    else:
        check("Sensitive content refused", FAIL, f"got {r.get('status')}")

    r = ask(conn, "send this to him", app="Gmail")
    if r.get("status") in ("ambiguous", "unclear"):
        check("Asks instead of guessing", PASS)
    else:
        check("Asks instead of guessing", FAIL, f"got {r.get('status')}")

    scope = conn.execute(
        """SELECT detail FROM trace_step WHERE stage='memory_scope'
           AND trace_id IN (SELECT id FROM trace WHERE surface='dictation')
           ORDER BY id DESC LIMIT 1""").fetchone()
    if scope and json.loads(scope["detail"]).get("reads") == ["fact"]:
        check("Dictation boundary enforced", PASS, "reads facts only")
    else:
        check("Dictation boundary enforced", FAIL, "scope step missing or wrong")

    traces = conn.execute("SELECT COUNT(*) c FROM trace").fetchone()["c"]
    steps = conn.execute("SELECT COUNT(*) c FROM trace_step").fetchone()["c"]
    check("Traces recorded", PASS if traces and steps else FAIL,
          f"{traces} traces, {steps} steps")
    conn.close()

    # 9. HTTP layer and interface ------------------------------------------
    from kivi.api import app as flask_app
    client = flask_app.test_client()

    s = client.get("/api/status")
    check("API responds", PASS if s.status_code == 200 else FAIL,
          f"/api/status → {s.status_code}")

    m = client.get("/api/memory")
    ok = m.status_code == 200 and "counts" in m.get_json()
    check("Memory surface serves", PASS if ok else FAIL, f"/api/memory → {m.status_code}")

    page = client.get("/")
    html = page.data.decode("utf-8", "replace")
    markers = ["<title>Kivi", "/api/ask", "/api/dictate", "What Kivi knows"]
    found = [x for x in markers if x in html]
    if page.status_code == 200 and len(found) == len(markers):
        check("Interface serves", PASS, f"{len(html):,} bytes, wired to the API")
    else:
        check("Interface serves", FAIL, f"status {page.status_code}, matched {len(found)}/{len(markers)}")

    # 10. port availability ------------------------------------------------
    port = int(os.environ.get("KIVI_PORT", "8000"))
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
        check(f"Port {port} is free", PASS)
    except OSError:
        check(f"Port {port} is free", WARN,
              f"something is already using it — start with: python run.py --port 8080")
    finally:
        sock.close()

    # cleanup ---------------------------------------------------------------
    dbmod.reset(SCRATCH)
    return report()


def report() -> int:
    failed = [n for n, s, _ in results if s == FAIL]
    warned = [n for n, s, _ in results if s == WARN]
    print("-" * 60)
    if failed:
        print(f"{len(failed)} check(s) FAILED:")
        for n in failed:
            print(f"  - {n}")
        print("\nFix these before submitting.")
        return 1
    if warned:
        print(f"All checks passed, {len(warned)} warning(s).")
    else:
        print("All checks passed. The system runs end to end.")
    print("\nNext: python run.py    then open http://127.0.0.1:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
