#!/usr/bin/env python3
"""Reproducible evaluation of the whole pipeline.

Runs every corpus record through the real ingestion path, then runs a fixed set
of Hey Kivi requests against the resulting database. Nothing is stubbed: the
same code serves the UI.

For every result the report keeps the original input, what memory was created,
retrieved, changed or rejected, where that memory came from, the resulting
behaviour, and the reason. Latency, database growth, model calls and cost are
recorded throughout.

    python evaluation/run_eval.py               # local backend, no key needed
    KIVI_LLM=anthropic python evaluation/run_eval.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kivi import corpus_io  # noqa: E402
from kivi.config import DB_PATH, POLICY  # noqa: E402
from kivi.db import connect, db_size_bytes, jload, reset  # noqa: E402
from kivi.heykivi.run import ask, dictate  # noqa: E402
from kivi.llm import get_backend  # noqa: E402
from kivi.memory import retrieve  # noqa: E402

CORPUS = ROOT / "corpus" / "corpus.jsonl"
OUT_JSON = ROOT / "evaluation" / "results.json"
OUT_MD = ROOT / "evaluation" / "REPORT.md"

# --------------------------------------------------------------------------
# Hey Kivi cases. `expect` names the behaviour, not the wording.
# --------------------------------------------------------------------------
CASES = [
    # the brief's own example, chained
    {"id": "chain_slack_5pm",
     "ask": "find the dictation I did around 5 PM yesterday in Slack and polish it for the meeting I'm walking into",
     "expect": {"intent": "find_dictation", "status": "found_and_reshaped",
                "episode_app": "Slack", "reshaped": True}},
    {"id": "find_plain",
     "ask": "find what I dictated in Gmail yesterday",
     "expect": {"intent": "find_dictation", "status_in": ["found", "ambiguous", "not_found"]}},
    {"id": "find_impossible",
     "ask": "find the dictation I did in Figma last Tuesday",
     "expect": {"intent": "find_dictation", "status_in": ["not_found", "ambiguous"]}},
    {"id": "recall_rules",
     "ask": "what rules are you following for my emails",
     "expect": {"intent": "recall", "status": "answered", "min_active": 1}},
    {"id": "recall_spelling",
     "ask": "how do you spell sharvam",
     "expect": {"intent": "recall", "status": "answered"}},
    {"id": "remember_new",
     "ask": "remember that I always sign off with just my first name",
     "expect": {"intent": "remember", "status": "remembered"}},
    {"id": "remember_refused",
     "ask": "remember that my portal password is kivi@2026",
     "expect": {"intent": "remember", "status": "declined"}},
    {"id": "forget_rule",
     "ask": "forget the rule about Dear Sir",
     "expect": {"intent": "forget", "status_in": ["forgotten", "ambiguous", "not_found"]}},
    {"id": "reshape_with_selection",
     "ask": "make this more concise but keep the technical meaning",
     "selection": "The implementation requires significant engineering effort and may not be "
                  "practical within the current timeline, so we have decided to report both "
                  "the full system and a reduced variant instead.",
     "expect": {"intent": "reshape", "status": "drafted", "changed": True}},
    {"id": "reshape_without_selection",
     "ask": "make this shorter",
     "expect": {"intent": "reshape", "status": "ambiguous", "field": "selection"}},
    {"id": "draft_named",
     "ask": "draft a message to Arjun saying the latency numbers are ready",
     "expect": {"intent": "draft_message", "status": "drafted", "not_sent": True}},
    {"id": "ambiguous_referent",
     "ask": "send this to him",
     "expect": {"status_in": ["ambiguous", "unclear"]}},
    {"id": "nonsense",
     "ask": "purple monday sideways",
     "expect": {"status_in": ["unclear", "not_found", "nothing_known", "ambiguous"]}},
]


def percent(a: int, b: int) -> str:
    return f"{(100.0 * a / b):.1f}%" if b else "n/a"


def main() -> int:
    t0 = time.time()
    reset(DB_PATH)
    conn = connect()
    backend = get_backend()
    backend_name = getattr(backend, "name", "local")

    records = [corpus_io.rebase(json.loads(line))
               for line in CORPUS.open(encoding="utf-8") if line.strip()]
    print(f"corpus: {len(records)} records · backend: {backend_name}")

    # ---------------- phase 1: ingestion ---------------------------------
    ing = {
        "fact_expected": 0, "fact_found": 0, "fact_direction_ok": 0,
        "pref_expected": 0, "pref_found": 0,
        "pref_observed_expected": 0, "pref_observed_ok": 0,
        "refuse_expected": 0, "refuse_ok": 0,
        "false_facts": 0, "false_prefs": 0,
        "reminder_expected": 0, "reminder_ok": 0,
    }
    latencies: list[float] = []
    growth: list[tuple[int, int]] = []
    cases: list[dict] = []

    for i, rec in enumerate(records):
        expect = rec.get("expect", {})
        payload = {k: v for k, v in rec.items() if k != "expect"}
        started = time.time()
        out = dictate(conn, payload)
        latencies.append((time.time() - started) * 1000.0)

        learned = out["learned"]
        made = learned["created"] + learned["reinforced"]
        kinds = {m["kind"] for m in made}
        bodies = {m["kind"]: [x["body"] for x in made if x["kind"] == m["kind"]] for m in made}

        # refusals
        if expect.get("refuse"):
            ing["refuse_expected"] += 1
            if not (kinds - {"episode"}) and not any(m["kind"] == "episode" for m in made):
                ing["refuse_ok"] += 1
        else:
            if "fact" in kinds and "fact" not in expect.get("kinds", []):
                ing["false_facts"] += 1
            if "preference" in kinds and "preference" not in expect.get("kinds", []):
                ing["false_prefs"] += 1

        if expect.get("fact"):
            ing["fact_expected"] += 1
            got = bodies.get("fact", [])
            if got:
                ing["fact_found"] += 1
                want = f"{expect['fact']['wrong']} → {expect['fact']['right']}"
                if any(g.lower() == want.lower() for g in got):
                    ing["fact_direction_ok"] += 1

        if expect.get("preference_active"):
            ing["pref_expected"] += 1
            if any(m["kind"] == "preference" and m.get("status") == "active" for m in made):
                ing["pref_found"] += 1

        if expect.get("preference_observed"):
            ing["pref_observed_expected"] += 1
            occ = expect.get("occurrence", 1)
            prefs = [m for m in made if m["kind"] == "preference"]
            if prefs:
                status = prefs[0].get("status")
                ok = (status == "observed") if occ < expect.get("promotes_at", 3) else (status == "active")
                if ok:
                    ing["pref_observed_ok"] += 1

        if expect.get("reminder"):
            ing["reminder_expected"] += 1
            reminders = [m for m in made if m["kind"] == "episode" and m["body"].startswith("Reminder:")]
            if reminders:
                ing["reminder_ok"] += 1

        if i % 50 == 0:
            growth.append((i, db_size_bytes(DB_PATH)))

        if expect.get("fact") or expect.get("refuse") or expect.get("preference_active") \
           or expect.get("reminder") or expect.get("preference_observed"):
            cases.append({
                "utterance_id": rec["id"],
                "input": rec["raw_asr"],
                "app": rec["app"],
                "expected": expect,
                "created": [{"kind": m["kind"], "body": m["body"], "status": m.get("status"),
                             "reason": m.get("reason"), "id": m.get("id")} for m in learned["created"]],
                "reinforced": [{"kind": m["kind"], "body": m["body"], "status": m.get("status"),
                                "observations": m.get("observations"), "reason": m.get("reason")}
                               for m in learned["reinforced"]],
                "conflicts": learned["conflicts"],
                "ignored": learned["ignored"],
                "trace_id": out["trace"]["id"],
                "latency_ms": out["trace"]["latency_ms"],
            })

    growth.append((len(records), db_size_bytes(DB_PATH)))

    counts = {}
    for kind in ("fact", "preference", "episode"):
        for status in ("active", "observed", "rejected", "retired"):
            n = conn.execute(
                "SELECT COUNT(*) c FROM memory WHERE kind=? AND status=?", (kind, status)
            ).fetchone()["c"]
            if n:
                counts[f"{kind}/{status}"] = n

    # ---------------- phase 2: retrieval ---------------------------------
    # Two kinds of case. A query naming content, a time and an app has one
    # right answer, so it is scored on rank. A query naming only a time and an
    # app has many right answers, so scoring it on rank would measure luck; it
    # is scored on whether every result satisfies the filters.
    retrieval_cases = [
        {"query": "find the dictation I did around 5 PM yesterday in Slack",
         "anchor": "slack_5pm_yesterday", "mode": "ranked"},
        {"query": "what did I say about the family lunch in WhatsApp yesterday",
         "anchor": "whatsapp_5pm_decoy", "mode": "ranked"},
        {"query": "what did I say in WhatsApp yesterday evening",
         "anchor": "whatsapp_5pm_decoy", "mode": "filtered"},
    ]
    anchors = {r["expect"].get("anchor"): r["id"] for r in records if r["expect"].get("anchor")}
    retrieval_results = []
    for case in retrieval_cases:
        query = case["query"]
        window = retrieve.parse_time_hint(query)
        app = retrieve.parse_app_hint(query)
        res = retrieve.search(conn, query, kinds=("episode",), app=app, window=window, top_k=5)
        want_utt = anchors.get(case["anchor"])
        rank = next((i + 1 for i, h in enumerate(res["hits"]) if h["source_utt"] == want_utt), None)

        if case["mode"] == "ranked":
            ok = rank == 1
        else:
            in_app = all((h["scope_app"] or "").lower() == (app or "").lower() for h in res["hits"])
            in_win = (all(window["start"] <= h["created_ts"] <= window["end"] for h in res["hits"])
                      if window else True)
            ok = bool(res["hits"]) and in_app and in_win

        retrieval_results.append({
            "query": query, "anchor": case["anchor"], "mode": case["mode"],
            "passed": ok, "rank": rank,
            "app_filter": app, "window": window["label"] if window else None,
            "filter_driven": res["filters"].get("filter_driven"),
            "considered": res["considered"],
            "hits": [{"score": h["score"], "app": h["scope_app"], "body": h["body"][:70],
                      "why": h["why"]} for h in res["hits"][:3]],
        })

    # ---------------- phase 3: end-to-end --------------------------------
    e2e = []
    for case in CASES:
        started = time.time()
        out = ask(conn, case["ask"], app=case.get("app"), selection=case.get("selection"))
        elapsed = (time.time() - started) * 1000.0
        exp = case["expect"]
        checks: dict[str, bool] = {}
        if "intent" in exp:
            checks["intent"] = out.get("intent") == exp["intent"]
        if "status" in exp:
            checks["status"] = out.get("status") == exp["status"]
        if "status_in" in exp:
            checks["status"] = out.get("status") in exp["status_in"]
        if exp.get("episode_app"):
            checks["episode_app"] = (out.get("episode") or {}).get("scope_app") == exp["episode_app"]
        if exp.get("reshaped"):
            checks["reshaped"] = bool((out.get("reshaped") or {}).get("after"))
        if exp.get("changed"):
            checks["changed"] = out.get("after") not in (None, out.get("before"))
        if exp.get("min_active"):
            checks["min_active"] = len(out.get("active", [])) >= exp["min_active"]
        if exp.get("field"):
            checks["field"] = out.get("field") == exp["field"]
        if exp.get("not_sent"):
            checks["not_sent"] = "not sent" in (out.get("note", "").lower())

        e2e.append({
            "id": case["id"], "ask": case["ask"], "selection": case.get("selection"),
            "intent": out.get("intent"), "confidence": out.get("confidence"),
            "status": out.get("status"), "say": out.get("say"),
            "checks": checks, "passed": all(checks.values()) if checks else None,
            "trace_id": out["trace"]["id"], "latency_ms": round(elapsed, 2),
            "usage": out["trace"]["usage"],
            "result": {k: v for k, v in out.items()
                       if k in ("episode", "reshaped", "after", "applied", "draft",
                                "active", "observed", "options", "reason", "memory")},
            "trace_steps": out["trace"]["steps"],
        })

    # ---------------- cost, latency, growth ------------------------------
    row = conn.execute(
        """SELECT COUNT(*) n, SUM(model_calls) calls, SUM(input_tokens) tin,
                  SUM(output_tokens) tout, SUM(cost_usd) cost FROM trace"""
    ).fetchone()
    lat = sorted(latencies)
    summary = {
        "backend": backend_name,
        "records": len(records),
        "wall_clock_s": round(time.time() - t0, 2),
        "ingest_latency_ms": {
            "p50": round(lat[len(lat) // 2], 2),
            "p95": round(lat[int(len(lat) * 0.95)], 2),
            "max": round(lat[-1], 2),
        },
        "db_bytes_final": db_size_bytes(DB_PATH),
        "db_bytes_per_record": round(db_size_bytes(DB_PATH) / max(1, len(records)), 1),
        "db_growth": growth,
        "traces": row["n"],
        "model_calls": row["calls"] or 0,
        "input_tokens": row["tin"] or 0,
        "output_tokens": row["tout"] or 0,
        "cost_usd": round(row["cost"] or 0.0, 4),
        "memory_counts": counts,
        "policy": {k: v for k, v in POLICY.items()},
    }

    scores = {
        "fact_recall": percent(ing["fact_found"], ing["fact_expected"]),
        "fact_direction_correct": percent(ing["fact_direction_ok"], ing["fact_expected"]),
        "preference_activation": percent(ing["pref_found"], ing["pref_expected"]),
        "observed_not_applied": percent(ing["pref_observed_ok"], ing["pref_observed_expected"]),
        "refusal": percent(ing["refuse_ok"], ing["refuse_expected"]),
        "reminder_capture": percent(ing["reminder_ok"], ing["reminder_expected"]),
        "false_facts": ing["false_facts"],
        "false_preferences": ing["false_prefs"],
        "retrieval": percent(sum(1 for r in retrieval_results if r["passed"]), len(retrieval_results)),
        "e2e_passed": percent(sum(1 for c in e2e if c["passed"]), len(e2e)),
    }

    results = {
        "summary": summary, "scores": scores, "counters": ing,
        "ingestion_cases": cases, "retrieval": retrieval_results, "end_to_end": e2e,
    }
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(results)

    print("\n" + "=" * 62)
    for k, v in scores.items():
        print(f"  {k:26s} {v}")
    print("=" * 62)
    print(f"  ingest p50 {summary['ingest_latency_ms']['p50']}ms · "
          f"p95 {summary['ingest_latency_ms']['p95']}ms")
    print(f"  db {summary['db_bytes_final']:,} bytes "
          f"({summary['db_bytes_per_record']} B/record)")
    print(f"  model calls {summary['model_calls']} · cost ${summary['cost_usd']}")
    print(f"\n  wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    failed = [c["id"] for c in e2e if c["passed"] is False]
    if failed:
        print(f"  FAILED: {', '.join(failed)}")
    return 0


def write_markdown(r: dict) -> None:
    s, sc = r["summary"], r["scores"]
    L = [
        "# Evaluation report", "",
        f"Backend `{s['backend']}` · {s['records']} records · "
        f"{s['wall_clock_s']}s wall clock · regenerate with `python evaluation/run_eval.py`", "",
        "## Scores", "",
        "| measure | result | what it means |",
        "| --- | --- | --- |",
        f"| Fact recall | {sc['fact_recall']} | corrections that produced a dictionary entry |",
        f"| Fact direction | {sc['fact_direction_correct']} | learned the correction, not the error |",
        f"| Preference activation | {sc['preference_activation']} | explicit rules that became active at once |",
        f"| Observed, not applied | {sc['observed_not_applied']} | inferred rules correctly held below the promotion gate |",
        f"| Refusal | {sc['refusal']} | sensitive and private utterances stored as nothing |",
        f"| Reminder capture | {sc['reminder_capture']} | reminders kept as episodes, not rules |",
        f"| False facts | {sc['false_facts']} | dictionary entries invented from ordinary speech |",
        f"| False preferences | {sc['false_preferences']} | rules invented from ordinary speech |",
        f"| Retrieval | {sc['retrieval']} | anchors ranked first, and filter-only queries returning only valid results |",
        f"| End-to-end | {sc['e2e_passed']} | Hey Kivi cases behaving as specified |",
        "", "## Cost, latency and growth", "",
        f"- ingest latency p50 **{s['ingest_latency_ms']['p50']} ms**, "
        f"p95 **{s['ingest_latency_ms']['p95']} ms**, max {s['ingest_latency_ms']['max']} ms",
        f"- database **{s['db_bytes_final']:,} bytes** after {s['records']} records "
        f"(**{s['db_bytes_per_record']} bytes/record**)",
        f"- model calls **{s['model_calls']}**, tokens in/out {s['input_tokens']}/{s['output_tokens']}, "
        f"cost **${s['cost_usd']}**",
        f"- memory after the run: " + ", ".join(f"`{k}` {v}" for k, v in s["memory_counts"].items()),
        "", "## End-to-end cases", "",
        "| case | intent | status | passed | trace |", "| --- | --- | --- | --- | --- |",
    ]
    for c in r["end_to_end"]:
        mark = "pass" if c["passed"] else ("—" if c["passed"] is None else "**FAIL**")
        L.append(f"| `{c['id']}` | {c['intent']} | {c['status']} | {mark} | `{c['trace_id']}` |")
    L += ["", "Open any trace at `/api/trace/<id>` while the app is running, or find it in "
              "`evaluation/results.json` under `end_to_end[].trace_steps`.", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
