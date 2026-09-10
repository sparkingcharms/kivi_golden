"""The tool set.

Five tools, chosen because the use cases need exactly these and no more:

    find_dictation   "find the thing I said around 5pm yesterday in Slack"
    reshape          "...and polish it for the meeting I'm walking into"
    recall           "what do you actually know about me"
    draft_message    "tell amma I'll be late"
    remember/forget  teaching and unteaching, by voice

Everything a tool returns is a proposal. No tool sends, posts, commits or
writes into another application. That is the position, enforced in code: the
transport is the person pressing Apply.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..config import POLICY
from ..db import jload
from ..memory import retrieve, store


def apply_shortcut(conn: sqlite3.Connection, shortcut: dict[str, Any], selection: str,
                   app: str | None, backend, trace) -> dict[str, Any]:
    """Run a shortcut the person defined against the current selection.

    Precedence matters here. The person's standing preferences go in first, the
    shortcut's own rules last, so the shortcut wins where they disagree: saying
    "professorize this" is an explicit instruction right now, and a general
    preference should not override an instruction.
    """
    standing = retrieve.active_rules(conn, app=app)
    payloads = [r["payload"] for r in standing] + [shortcut["rules"]]
    trace.step("shortcut_rules",
               shortcut=shortcut["phrase"],
               shortcut_rules=shortcut["rules"],
               standing=[r["body"] for r in standing],
               precedence="standing preferences first, shortcut last")

    result, usage = backend.reshape(selection, payloads, shortcut["body"])
    trace.add_usage(usage)

    applied = result.get("applied", [])
    store.mark_used(conn, [shortcut["id"]], trace.id)
    trace.step("shortcut_applied", phrase=shortcut["phrase"], applied=applied,
               unchanged=not applied)

    return {
        "status": "drafted",
        "via_shortcut": shortcut["phrase"],
        "definition": shortcut["understood"] or [shortcut["body"]],
        "before": selection,
        "after": result.get("text", selection),
        "applied": applied,
        "not_executable": shortcut["not_executable"],
        "note": f"“{shortcut['phrase']}” applied. Nothing has changed until you press Apply.",
    }


def find_dictation(conn, query: str, trace) -> dict[str, Any]:
    window = retrieve.parse_time_hint(query)
    app = retrieve.parse_app_hint(query)
    trace.step("parse_reference", time_window=window, app=app)

    result = retrieve.search(
        conn, query, kinds=("episode",), app=app, window=window, top_k=5
    )
    trace.step("retrieve", **_summarise(result))

    if not result["hits"]:
        return {
            "status": "not_found",
            "say": _nothing_found(window, app),
            "candidates": [],
            "retrieval": result,
        }

    top = result["hits"][0]
    runner_up = result["hits"][1] if len(result["hits"]) > 1 else None
    if runner_up and (top["score"] - runner_up["score"]) < 0.05:
        return {
            "status": "ambiguous",
            "say": "Two of these match. Which one did you mean?",
            "candidates": result["hits"][:3],
            "retrieval": result,
        }
    return {
        "status": "found",
        "say": "Found it.",
        "episode": top,
        "candidates": result["hits"][:3],
        "retrieval": result,
    }


def reshape(conn: sqlite3.Connection, text: str, instruction: str, app: str | None,
            backend, trace) -> dict[str, Any]:
    rules = retrieve.active_rules(conn, app=app)
    trace.step("rules_in_force", count=len(rules),
               rules=[{"id": r["id"], "body": r["body"]} for r in rules])

    payloads = [r["payload"] for r in rules]
    result, usage = backend.reshape(text, payloads, instruction)
    trace.add_usage(usage)

    applied_labels = result.get("applied", [])
    applied_ids = [
        r["id"] for r in rules
        if any(lbl.lower() in r["body"].lower() or r["body"].lower() in lbl.lower()
               for lbl in applied_labels)
    ]
    trace.step("reshape", instruction=instruction, applied=applied_labels,
               applied_memory_ids=applied_ids,
               unused_rules=[r["body"] for r in rules if r["id"] not in applied_ids])

    return {
        "status": "drafted",
        "before": text,
        "after": result.get("text", text),
        "applied": applied_labels,
        "applied_memory_ids": applied_ids,
        "rules_considered": [r["body"] for r in rules],
    }


def recall(conn: sqlite3.Connection, query: str, trace) -> dict[str, Any]:
    result = retrieve.search(
        conn, query, kinds=("fact", "preference"), include_observed=True, top_k=8
    )
    trace.step("retrieve", **_summarise(result))
    active = [h for h in result["hits"] if h["status"] == "active"]
    observed = [h for h in result["hits"] if h["status"] == "observed"]
    return {
        "status": "answered" if result["hits"] else "nothing_known",
        "say": "Here is what I am going by." if active else "Nothing is in force for that yet.",
        "active": active,
        "observed": observed,
        "retrieval": result,
    }


def draft_message(conn: sqlite3.Connection, request: str, app: str | None,
                  backend, trace) -> dict[str, Any]:
    recipient, ambiguity = _resolve_recipient(conn, request, trace)
    if ambiguity:
        return {"status": "ambiguous", "say": ambiguity["say"],
                "options": ambiguity["options"], "field": "recipient"}

    facts = retrieve.dictionary(conn)
    rules = retrieve.active_rules(conn, app=app)
    trace.step("rules_in_force", count=len(rules),
               rules=[{"id": r["id"], "body": r["body"]} for r in rules])

    body = _strip_request_verbs(request)
    body, corrected = retrieve.apply_dictionary(body, facts)
    if corrected:
        trace.step("dictionary", replaced=[c["body"] for c in corrected])

    result, usage = backend.reshape(body, [r["payload"] for r in rules], request)
    trace.add_usage(usage)
    trace.step("draft", recipient=recipient, applied=result.get("applied", []))

    return {
        "status": "drafted",
        "recipient": recipient,
        "draft": result.get("text", body),
        "applied": result.get("applied", []),
        "note": "Drafted, not sent. It opens in the app for you to send.",
    }


def remember(conn: sqlite3.Connection, statement: str, trace) -> dict[str, Any]:
    from ..local_model import sensitivity

    label = sensitivity(statement)
    if label:
        trace.step("refused", category=label)
        return {
            "status": "declined",
            "say": f"I will not keep that. It looks like {label.replace('_', ' ')}, "
                   "which Kivi never stores.",
        }
    body = _strip_teach_verbs(statement)
    out = store.teach(conn, "preference", body)
    trace.step("teach", **out)
    return {
        "status": "remembered",
        "say": f"Kept: {body}",
        "memory": out,
    }


def forget(conn: sqlite3.Connection, query: str, trace) -> dict[str, Any]:
    result = retrieve.search(conn, query, kinds=("fact", "preference"),
                             include_observed=True, top_k=3)
    trace.step("retrieve", **_summarise(result))
    if not result["hits"]:
        return {"status": "not_found", "say": "I could not find a rule matching that."}
    if len(result["hits"]) > 1 and (result["hits"][0]["score"] - result["hits"][1]["score"]) < 0.08:
        return {"status": "ambiguous", "say": "Which one should I drop?",
                "options": result["hits"][:3], "field": "memory"}
    target = result["hits"][0]
    out = store.retire(conn, target["id"], "you asked Kivi to forget it")
    trace.step("retire", **out)
    return {"status": "forgotten", "say": f"Dropped: {target['body']}", "memory": target}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_PRONOUNS = ("him", "her", "them", "that one", "it")


def _resolve_recipient(conn, request: str, trace) -> tuple[str | None, dict | None]:
    """Named people resolve. Pronouns with more than one candidate always ask —
    this is the case the brief asks about: incomplete understanding surfacing
    as a question rather than a guess."""
    import re

    m = re.search(r"\b(?:to|tell|for)\s+(?P<name>[A-Z][\w]+|amma|appa|the team|my professor)\b", request)
    if m:
        return m.group("name"), None

    if any(p in request.lower() for p in _PRONOUNS) and POLICY["ambiguous_referent_asks"]:
        people = conn.execute(
            """SELECT DISTINCT body, payload FROM memory
               WHERE kind='fact' AND status='active'"""
        ).fetchall()
        names = []
        for r in people:
            p = jload(r["payload"])
            if p.get("flavour") in ("correction", "spelling") and p.get("right", "").istitle():
                names.append(p["right"])
        names = sorted(set(names))[:3]
        if len(names) > 1:
            trace.step("ambiguous_referent", candidates=names)
            return None, {
                "say": f"Two people could be that here, and nothing is selected.",
                "options": names,
            }
    return None, None


def _strip_request_verbs(text: str) -> str:
    import re
    t = re.sub(r"^\s*(?:hey kivi[,\s]*)?", "", text, flags=re.I)
    t = re.sub(r"^\s*(?:draft|write|send|tell|reply to)\s+(?:a\s+)?(?:message|note|email|reply)?\s*",
               "", t, flags=re.I)
    t = re.sub(r"^\s*(?:to\s+)?[A-Z]\w+\s*(?:saying|that)?\s*", "", t)
    t = re.sub(r"^\s*(?:amma|appa|the team|my professor)\s*(?:saying|that)?\s*", "", t, flags=re.I)
    return t.strip() or text.strip()


def _strip_teach_verbs(text: str) -> str:
    import re
    t = re.sub(r"^\s*(?:hey kivi[,\s]*)?", "", text, flags=re.I)
    t = re.sub(r"^\s*(?:remember(?:\s+that|\s+this)?|note that|from now on)[,:\s]*", "", t, flags=re.I)
    t = t.strip()
    return (t[:1].upper() + t[1:]) if t else text


def _summarise(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "considered": result["considered"],
        "floor": result["floor"],
        "filters": result["filters"],
        "hits": [{"id": h["id"], "score": h["score"], "body": h["body"][:90], "why": h["why"]}
                 for h in result["hits"]],
        "below_floor": [{"id": h["id"], "score": h["score"], "body": h["body"][:60],
                         "why": h["why"]} for h in result["below_floor"]],
    }


def _nothing_found(window: dict | None, app: str | None) -> str:
    bits = []
    if window:
        bits.append(window["label"])
    if app:
        bits.append(f"in {app}")
    where = " ".join(bits) if bits else "matching that"
    return f"Nothing {where}. Widen the time, or tell me the app."
