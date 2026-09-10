"""The tool set.

Five tools, chosen because the use cases need exactly these and no more.
Everything a tool returns is a proposal. No tool sends, posts, commits or
writes into another application.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..config import POLICY
from ..db import jload
from ..memory import retrieve, store


def find_dictation(conn, query, trace):
    window = retrieve.parse_time_hint(query); app = retrieve.parse_app_hint(query)
    trace.step("parse_reference", time_window=window, app=app)
    result = retrieve.search(conn, query, kinds=("episode",), app=app, window=window, top_k=5)
    trace.step("retrieve", **_summarise(result))
    if not result["hits"]:
        return {"status":"not_found","say":_nothing_found(window,app),"candidates":[],"retrieval":result}
    top=result["hits"][0]; runner_up=result["hits"][1] if len(result["hits"])>1 else None
    if runner_up and top["score"]-runner_up["score"]<0.05:
        return {"status":"ambiguous","say":"Two of these match. Which one did you mean?","candidates":result["hits"][:3],"retrieval":result}
    return {"status":"found","say":"Found it.","episode":top,"candidates":result["hits"][:3],"retrieval":result}


def reshape(conn,text,instruction,app,backend,trace):
    rules=retrieve.active_rules(conn,app=app)
    trace.step("rules_in_force",count=len(rules),rules=[{"id":r["id"],"body":r["body"]} for r in rules])
    result,usage=backend.reshape(text,[r["payload"] for r in rules],instruction); trace.add_usage(usage)
    applied_labels=result.get("applied",[])
    applied_ids=[r["id"] for r in rules if any(lbl.lower() in r["body"].lower() or r["body"].lower() in lbl.lower() for lbl in applied_labels)]
    trace.step("reshape",instruction=instruction,applied=applied_labels,applied_memory_ids=applied_ids,unused_rules=[r["body"] for r in rules if r["id"] not in applied_ids])
    return {"status":"drafted","before":text,"after":result.get("text",text),"applied":applied_labels,"applied_memory_ids":applied_ids,"rules_considered":[r["body"] for r in rules]}


def apply_shortcut(conn, shortcut, selection, app, backend, trace):
    """Apply a matched shortcut as a proposal; the caller remains responsible for transport."""
    if not selection:
        trace.step("shortcut_missing_selection", phrase=shortcut["phrase"])
        return {"status":"needs_selection","say":f"Select the text you want “{shortcut['phrase']}” applied to.","shortcut":shortcut}
    result, usage = backend.reshape(selection, list(shortcut.get("rules", {}).values()) if isinstance(shortcut.get("rules"), dict) else [], shortcut.get("meaning", shortcut.get("body", "")))
    trace.add_usage(usage)
    trace.step("shortcut_applied", phrase=shortcut["phrase"], rules=shortcut.get("rules", {}), not_executable=shortcut.get("not_executable", []))
    return {"status":"drafted","before":selection,"after":result.get("text",selection),"applied":result.get("applied",[]),"via_shortcut":shortcut["phrase"],"note":"Shortcut proposed; nothing changed until Apply."}


def recall(conn,query,trace):
    result=retrieve.search(conn,query,kinds=("fact","preference"),include_observed=True,top_k=8); trace.step("retrieve",**_summarise(result))
    active=[h for h in result["hits"] if h["status"]=="active"]; observed=[h for h in result["hits"] if h["status"]=="observed"]
    return {"status":"answered" if result["hits"] else "nothing_known","say":"Here is what I am going by." if active else "Nothing is in force for that yet.","active":active,"observed":observed,"retrieval":result}


def draft_message(conn,request,app,backend,trace):
    recipient,ambiguity=_resolve_recipient(conn,request,trace)
    if ambiguity:return {"status":"ambiguous","say":ambiguity["say"],"options":ambiguity["options"],"field":"recipient"}
    facts=retrieve.dictionary(conn); rules=retrieve.active_rules(conn,app=app); trace.step("rules_in_force",count=len(rules),rules=[{"id":r["id"],"body":r["body"]} for r in rules])
    body=_strip_request_verbs(request); body,corrected=retrieve.apply_dictionary(body,facts)
    if corrected:trace.step("dictionary",replaced=[c["body"] for c in corrected])
    result,usage=backend.reshape(body,[r["payload"] for r in rules],request);trace.add_usage(usage);trace.step("draft",recipient=recipient,applied=result.get("applied",[]))
    return {"status":"drafted","recipient":recipient,"draft":result.get("text",body),"applied":result.get("applied",[]),"note":"Drafted, not sent. It opens in the app for you to send."}


def remember(conn,statement,trace):
    from ..local_model import sensitivity
    label=sensitivity(statement)
    if label:
        trace.step("refused",category=label); return {"status":"declined","say":f"I will not keep that. It looks like {label.replace('_',' ')}, which Kivi never stores."}
    body=_strip_teach_verbs(statement); out=store.teach(conn,"preference",body);trace.step("teach",**out);return {"status":"remembered","say":f"Kept: {body}","memory":out}


def forget(conn,query,trace):
    result=retrieve.search(conn,query,kinds=("fact","preference"),include_observed=True,top_k=3);trace.step("retrieve",**_summarise(result))
    if not result["hits"]:return {"status":"not_found","say":"I could not find a rule matching that."}
    if len(result["hits"])>1 and result["hits"][0]["score"]-result["hits"][1]["score"]<0.08:return {"status":"ambiguous","say":"Which one should I drop?","options":result["hits"][:3],"field":"memory"}
    target=result["hits"][0];out=store.retire(conn,target["id"],"you asked Kivi to forget it");trace.step("retire",**out);return {"status":"forgotten","say":f"Dropped: {target['body']}","memory":target}


_PRONOUNS=("him","her","them","that one","it")

def _resolve_recipient(conn,request,trace):
    import re
    m=re.search(r"\b(?:to|tell|for)\s+(?P<name>[A-Z][\w]+|amma|appa|the team|my professor)\b",request)
    if m:return m.group("name"),None
    if any(p in request.lower() for p in _PRONOUNS) and POLICY["ambiguous_referent_asks"]:
        people=conn.execute("SELECT DISTINCT body,payload FROM memory WHERE kind='fact' AND status='active'").fetchall();names=[]
        for r in people:
            p=jload(r["payload"])
            if p.get("flavour") in ("correction","spelling") and p.get("right","").istitle():names.append(p["right"])
        names=sorted(set(names))[:3]
        if len(names)>1:trace.step("ambiguous_referent",candidates=names);return None,{"say":"Two people could be that here, and nothing is selected.","options":names}
    return None,None


def _strip_request_verbs(text):
    import re
    t=re.sub(r"^\s*(?:hey kivi[,\s]*)?","",text,flags=re.I);t=re.sub(r"^\s*(?:draft|write|send|tell|reply to)\s+(?:a\s+)?(?:message|note|email|reply)?\s*","",t,flags=re.I);t=re.sub(r"^\s*(?:to\s+)?[A-Z]\w+\s*(?:saying|that)?\s*","",t);t=re.sub(r"^\s*(?:amma|appa|the team|my professor)\s*(?:saying|that)?\s*","",t,flags=re.I);return t.strip() or text.strip()

def _strip_teach_verbs(text):
    import re
    t=re.sub(r"^\s*(?:hey kivi[,\s]*)?","",text,flags=re.I);t=re.sub(r"^\s*(?:remember(?:\s+that|\s+this)?|note that|from now on)[,:\s]*","",t,flags=re.I);t=t.strip();return (t[:1].upper()+t[1:]) if t else text

def _summarise(result):
    return {"considered":result["considered"],"floor":result["floor"],"filters":result["filters"],"hits":[{"id":h["id"],"score":h["score"],"body":h["body"][:90],"why":h["why"]} for h in result["hits"]],"below_floor":[{"id":h["id"],"score":h["score"],"body":h["body"][:60],"why":h["why"]} for h in result["below_floor"]]}

def _nothing_found(window,app):
    bits=[]
    if window:bits.append(window["label"])
    if app:bits.append(f"in {app}")
    return f"Nothing {' '.join(bits) if bits else 'matching that'}. Widen the time, or tell me the app."
