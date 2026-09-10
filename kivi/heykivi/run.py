"""Orchestration for both surfaces.

`dictate()` is ordinary dictation. It reads facts and nothing else. A
preference you taught last week does not silently reshape a message you are
typing into WhatsApp; that would be Kivi rewriting your intent, which the
product refuses to do.

`ask()` is Hey Kivi. It reads everything, chains tools when the request needs
two of them, and abstains rather than guessing when the intent is unclear.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..config import POLICY
from ..llm import get_backend
from ..memory import retrieve, shortcuts, store
from ..trace import Trace
from . import tools

_CHAIN = re.compile(
    r"\b(?:and|then)\b.{0,40}?\b(polish|clean|shorten|make it|rewrite|tighten|turn it into)\b",
    re.I,
)


def dictate(conn: sqlite3.Connection, record: dict[str, Any]) -> dict[str, Any]:
    trace = Trace(conn, "dictation", record.get("raw_asr", ""), record.get("app"))
    entries = retrieve.dictionary(conn)
    trace.step("memory_scope", reads=list(POLICY["dictation_reads"]),
               reason="ordinary dictation may fix spellings, never reshape wording",
               dictionary_size=len(entries))
    text = record.get("formatted") or record.get("raw_asr") or ""
    corrected, used = retrieve.apply_dictionary(text, entries)
    trace.step("dictionary", replaced=[u["body"] for u in used], changed=corrected != text)
    record = {**record, "formatted": corrected}
    report = store.ingest(conn, record)
    trace.step("learn", created=[c["body"][:80] for c in report["created"]],
               reinforced=[c["body"][:80] for c in report["reinforced"]],
               conflicts=[c["body"][:80] for c in report["conflicts"]], ignored=report["ignored"])
    if used:
        store.mark_used(conn, [u["id"] for u in used], trace.id)
    info = trace.finish("answered")
    return {"text": corrected, "was": text if corrected != text else None,
            "corrections": used, "learned": report, "trace": info}


def ask(conn: sqlite3.Connection, request: str, app: str | None = None,
        selection: str | None = None, backend=None) -> dict[str, Any]:
    backend = backend or get_backend()
    trace = Trace(conn, "heykivi", request, app)
    trace.step("memory_scope", reads=list(POLICY["heykivi_reads"]),
               reason="an interactive request may use everything Kivi knows")

    taught = shortcuts.parse_teaching(request)
    if taught:
        draft = shortcuts.interpret(taught["phrase"], taught["meaning"], apps=[app] if app else [])
        trace.intent, trace.intent_conf = "teach_shortcut", 0.95
        trace.step("shortcut_interpreted", phrase=draft["phrase"],
                   understood=[u["text"] for u in draft["understood"]],
                   not_executable=draft["not_executable"])
        info = trace.finish("asked")
        return {"status": "shortcut_draft",
                "say": f"Here is how I read “{draft['phrase']}”. Correct anything, then save it.",
                "draft": draft, "intent": "teach_shortcut", "trace": info}

    hit = shortcuts.match(conn, request, app, bool(selection), trace)
    if hit:
        trace.intent, trace.intent_conf = "shortcut", hit.get("score", 1.0)
        if hit["status"] == "matched":
            result = tools.apply_shortcut(conn, hit["shortcut"], selection, app, backend, trace)
            if hit.get("near_miss"):
                result["near_miss"] = hit["near_miss"]
            info = trace.finish("answered")
            return {**result, "intent": "shortcut", "trace": info}
        info = trace.finish("asked")
        return {**hit, "intent": "shortcut", "trace": info}

    routed, usage = backend.classify_intent(request)
    trace.add_usage(usage)
    intent = routed.get("intent", "reshape")
    conf = float(routed.get("confidence", 0.0))
    scores = routed.get("scores", {})
    trace.intent, trace.intent_conf = intent, conf
    ranked = sorted(scores.values(), reverse=True) if scores else [conf]
    margin = (ranked[0] - ranked[1]) if len(ranked) > 1 else 1.0
    trace.step("route", intent=intent, confidence=conf, margin=round(margin, 4),
               scores=scores, floor=POLICY["intent_floor"])
    if conf < POLICY["intent_floor"] or margin < POLICY["intent_margin"]:
        top2 = sorted(scores, key=lambda k: scores[k], reverse=True)[:2] if scores else [intent]
        info = trace.finish("asked")
        return {"status": "unclear", "say": "I am not sure what you want done with that.",
                "options": [_INTENT_LABELS.get(i, i) for i in top2],
                "reason": f"confidence {conf:.2f} against a floor of {POLICY['intent_floor']}"
                          if conf < POLICY["intent_floor"] else f"two readings within {margin:.2f}",
                "trace": info}

    result = _dispatch(conn, intent, request, app, selection, backend, trace)
    if intent == "find_dictation" and result.get("status") == "found" and _CHAIN.search(request):
        trace.step("chain", reason="the request asks for a change after the lookup")
        text = result["episode"]["body"]
        second = tools.reshape(conn, text, request, app, backend, trace)
        result = {**result, "status": "found_and_reshaped", "reshaped": second}
        if second.get("applied_memory_ids"):
            store.mark_used(conn, second["applied_memory_ids"], trace.id)
    outcome = {"found": "answered", "found_and_reshaped": "answered", "drafted": "answered",
               "answered": "answered", "remembered": "answered", "forgotten": "answered",
               "ambiguous": "asked", "unclear": "asked", "not_found": "none",
               "ambiguous_trigger": "asked", "out_of_scope": "asked", "needs_selection": "asked",
               "shortcut_draft": "asked", "nothing_known": "none", "declined": "declined"}.get(
                   result.get("status", ""), "answered")
    info = trace.finish(outcome)
    return {**result, "intent": intent, "confidence": conf, "trace": info}


_INTENT_LABELS = {
    "find_dictation": "find something you dictated", "reshape": "rewrite what is selected",
    "recall": "tell you what Kivi knows", "draft_message": "draft a message",
    "remember": "remember a rule", "forget": "drop a rule",
}


def _dispatch(conn, intent, request, app, selection, backend, trace) -> dict[str, Any]:
    if intent == "find_dictation": return tools.find_dictation(conn, request, trace)
    if intent == "reshape":
        if not selection:
            trace.step("missing_input", needs="selection")
            return {"status": "ambiguous", "say": "Select the text you want changed first.",
                    "options": [], "field": "selection"}
        return tools.reshape(conn, selection, request, app, backend, trace)
    if intent == "recall": return tools.recall(conn, request, trace)
    if intent == "draft_message": return tools.draft_message(conn, request, app, backend, trace)
    if intent == "remember": return tools.remember(conn, request, trace)
    if intent == "forget": return tools.forget(conn, request, trace)
    return {"status": "unclear", "say": "I do not have a tool for that."}
