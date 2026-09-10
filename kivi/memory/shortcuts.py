"""Shortcuts — a phrase you invented, bound to an instruction you wrote.

    "professorize this"  →  formal, three sentences maximum, one clear ask,
                            no stacked apologies, fires on a selection in
                            Gmail and Slack

A shortcut is the fourth memory kind. It deliberately reuses everything the
other three already have — status, promotion, scope, provenance, the event log,
the trace — rather than getting its own machinery. That reuse is the point: if
the memory architecture only worked for spellings and tone rules, it was not
really an architecture.

Three things here are worth reading closely.

**Interpretation is not permission.** Teaching a shortcut does not save it.
`interpret()` reads back what Kivi understood, as numbered lines in your own
words, and returns a draft. Nothing is stored until `save()` is called with
that draft, edited or not. This is the same principle as the promotion gate,
applied at the moment of teaching instead of after three sightings.

**Collisions are a first-class problem.** "short version" and "shorter version"
sound alike. If two triggers match closely enough, Kivi refuses to pick and
asks, and it records the near-miss so the interface can suggest renaming one.
Silently guessing right most of the time is worse than asking: the failures are
invisible and land in sent messages.

**Scope is enforced, not decorative.** A shortcut declared for Gmail does not
fire in Cursor. When you say it in the wrong place Kivi says so, rather than
doing nothing and leaving you to wonder whether it heard you.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from difflib import SequenceMatcher
from typing import Any

from ..config import POLICY
from ..db import jdump, jload, now
from ..local_model import _compile_rule, bag, cosine, content_tokens, normalise_key


def phrase_similarity(a: str, b: str) -> float:
    """How alike do two trigger phrases sound?

    Word overlap is the wrong instrument here. "professorize this" and
    "professorise this" share only the word "this", and "short version" and
    "shorter version" share only "version" — a token comparison scores both
    pairs at 0.5 and sees no problem, while a recogniser will confuse them
    constantly. Character-level similarity catches exactly this class, which is
    the class that actually causes the wrong shortcut to fire.
    """
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return 0.0
    chars = SequenceMatcher(None, a, b).ratio()
    tokens = cosine(bag(a), bag(b))
    return round(max(chars, tokens), 4)


def _window_similarity(said_key: str, trigger: str) -> float:
    """Best match for the whole trigger anywhere inside what was said."""
    words = said_key.split()
    width = max(1, len(trigger.split()))
    best = 0.0
    for i in range(max(1, len(words) - width + 1)):
        window = " ".join(words[i:i + width])
        best = max(best, phrase_similarity(window, trigger))
    return round(best, 4)


def _head_similarity(said: str, trigger: str) -> float:
    """How well the trigger's distinctive word appears in what was said.

    Compared against single words and adjacent pairs, because a recogniser
    splits an invented compound unpredictably: "amma-mode" comes back as
    "amma mode" about as often as it comes back whole.
    """
    heads = [t for t in content_tokens(trigger) if t not in DEICTIC] \
        or content_tokens(trigger)
    toks = content_tokens(said) or [said]
    grams = list(toks)
    grams += [f"{toks[i]} {toks[i + 1]}" for i in range(len(toks) - 1)]
    grams += [f"{toks[i]}-{toks[i + 1]}" for i in range(len(toks) - 1)]
    best = 0.0
    for h in heads:
        for g in grams:
            best = max(best, phrase_similarity(h, g))
    return round(best, 4)

# Two triggers closer than this are treated as a collision rather than a match.
COLLISION_MARGIN = 0.18

# Below this a spoken phrase is not considered a shortcut at all, and the
# request falls through to ordinary intent classification.
#
# The gate is the trigger's *head* — its distinctive word, with deictics like
# "this" removed. Whole-phrase similarity cannot do this job: "make this
# shorter" scores 0.63 against the trigger "guard this" purely because both
# end in "this", and at a 0.62 floor a shortcut about code would fire on every
# rewrite request. Measured over the corpus triggers, head matching separates
# genuine matches (weakest 0.96) from non-matches (strongest 0.55) with a wide
gap, so the floor sits in the middle of it.
TRIGGER_FLOOR = 0.75

# Words that locate but do not identify. A trigger is not recognisable by them.
DEICTIC = {"this", "that", "it", "these", "those", "them", "here",
           "mine", "my", "the", "a", "an"}

FIRES_ON = ("selection", "voice", "any")

_TEACH = re.compile(
    r"^\s*(?:hey kivi[,\s]*)?(?:teach (?:me )?a shortcut[:,]?\s*)?"
    r"[\"“']?(?P<phrase>[\w' -]{2,40}?)[\"”']?\s+"
    r"(?:means|should mean|means that|=)\s+(?P<meaning>.{6,300})$",
    re.I,
)


def _id() -> str:
    return f"mem_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# teaching
# --------------------------------------------------------------------------

def parse_teaching(text: str) -> dict[str, str] | None:
    """Recognise 'professorize this means formal, three sentences, one ask'."""
    m = _TEACH.search(text or "")
    if not m:
        return None
    phrase = m.group("phrase").strip().strip("\"'“”")
    meaning = m.group("meaning").strip().rstrip(".")
    if len(phrase.split()) > 5 or not meaning:
        return None
    return {"phrase": phrase, "meaning": meaning}


def interpret(phrase: str, meaning: str, apps: list[str] | None = None,
              fires_on: str = "selection", examples: list[str] | None = None) -> dict[str, Any]:
    """Read the definition back as separate, editable lines. Saves nothing.

    Returns a draft the caller shows to the person. Every line is something
    they can correct before it becomes real, which is the whole point: a
    shortcut Kivi misunderstood is worse than no shortcut, because it fires
    silently and confidently.
    """
    lines = _split_clauses(meaning)
    rules = _compile_rule(meaning)
    understood = [
        {"n": i + 1, "text": line, "structured": _line_is_structured(line, rules)}
        for i, line in enumerate(lines)
    ]
    unstructured = [u["text"] for u in understood if not u["structured"]]
    return {
        "phrase": phrase,
        "trigger": normalise_key(phrase),
        "meaning": meaning,
        "understood": understood,
        "rules": rules,
        "apps": apps or [],
        "fires_on": fires_on if fires_on in FIRES_ON else "selection",
        "examples": examples or [],
        # Said out loud rather than buried: these lines were read but cannot be
        # executed deterministically by the local backend.
        "not_executable": unstructured,
        "status": "draft",
    }


def _split_clauses(meaning: str) -> list[str]:
    # Split on punctuation only. Splitting on "and" tears "add null and
    # empty-input checks" into two fragments that mean nothing apart.
    parts = re.split(r"\s*[,;. ]\s*", meaning)
    out = []
    for p in parts:
        p = p.strip(" .,;")
        if len(p.split()) >= 2:
            out.append(p[:1].upper() + p[1:])
    return out or [meaning.strip()]


_RULE_WORDS = {
    "max_sentences": ("sentence",), "bullets": ("bullet",), "no_apology": ("apolog",),
    "no_formal_greeting": ("dear sir", "madam"), "no_hedging": ("hedg", "adjective", "fluff", "filler"),
    "register": ("formal", "casual", "warm", "friendly"), "single_ask": ("ask",),
    "language": ("tamil", "hindi", "telugu", "english", "kannada"),
}


def _line_is_structured(line: str, rules: dict[str, Any]) -> bool:
    low = line.lower()
    for key, words in _RULE_WORDS.items():
        if key in rules and any(w in low for w in words):
            return True
    return False


def save(conn: sqlite3.Connection, draft: dict[str, Any], utt_id: str | None = None) -> dict[str, Any]:
    """Commit a reviewed draft. Refuses to overwrite an existing trigger."""
    trigger = draft.get("trigger") or normalise_key(draft.get("phrase", ""))
    if not trigger:
        return {"error": "no trigger phrase"}

    existing = conn.execute(
        "SELECT * FROM memory WHERE kind='shortcut' AND subject=? AND status='active'",
        (trigger,),
    ).fetchone()
    if existing:
        return {"status": "exists", "id": existing["id"], "body": existing["body"],
                "say": f"“{draft['phrase']}” already means something. Edit it or pick another phrase."}

    near = _nearest(conn, trigger, exclude=None)
    mid = _id()
    payload = {
        "trigger": trigger, "phrase": draft["phrase"], "meaning": draft["meaning"],
        "understood": [u["text"] for u in draft.get("understood", [])],
        "rules": draft.get("rules", {}),
        "apps": draft.get("apps", []),
        "fires_on": draft.get("fires_on", "selection"),
        "examples": draft.get("examples", []),
        "not_executable": draft.get("not_executable", []),
    }
    t = now()
    conn.execute(
        """INSERT INTO memory
           (id, kind, subject, body, payload, status, confidence, observations,
            scope_app, created_ts, updated_ts, source_utt, origin, reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, "shortcut", trigger, draft["meaning"], jdump(payload), "active", 0.97, 1,
         (draft.get("apps") or [None])[0], t, t, utt_id, "taught",
         "you defined this phrase yourself"),
    )
    conn.execute(
        "INSERT INTO memory_event (memory_id, ts, event, detail, utt_id) VALUES (?,?,?,?,?)",
        (mid, t, "promoted", "taught and confirmed", utt_id),
    )
    conn.commit()

    out = {"status": "saved", "id": mid, "phrase": draft["phrase"], "trigger": trigger,
           "fires_on": payload["fires_on"], "apps": payload["apps"]}
    # Warn at teaching time, not after it has fired wrongly twice.
    if near and near["score"] >= 1 - COLLISION_MARGIN * 2:
        out["warning"] = {
            "against": near["body"], "against_id": near["id"], "score": near["score"],
            "say": f"“{draft['phrase']}” sounds close to “{near['phrase']}”. "
                   f"Kivi may confuse them — consider renaming one.",
        }
    return out


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

def _all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM memory WHERE kind='shortcut' AND status='active' ORDER BY use_count DESC"
    ).fetchall()
    out = []
    for r in rows:
        p = jload(r["payload"])
        out.append({
            "id": r["id"], "trigger": r["subject"], "phrase": p.get("phrase", r["subject"]),
            "body": r["body"], "rules": p.get("rules", {}), "apps": p.get("apps", []),
            "fires_on": p.get("fires_on", "selection"),
            "understood": p.get("understood", []),
            "not_executable": p.get("not_executable", []),
            "use_count": r["use_count"], "created_ts": r["created_ts"],
            "source_utt": r["source_utt"],
        })
    return out


def _nearest(conn: sqlite3.Connection, trigger: str, exclude: str | None) -> dict | None:
    best = None
    for s in _all(conn):
        if s["id"] == exclude:
            continue
        score = phrase_similarity(trigger, s["trigger"])
        if best is None or score > best["score"]:
            best = {**s, "score": score}
    return best


def match(conn: sqlite3.Connection, said: str, app: str | None,
          has_selection: bool, trace=None) -> dict[str, Any] | None:
    """Is this utterance a shortcut? Returns None to fall through to routing.

    Scoring is containment-first: a shortcut is a phrase the person says at the
    start of a request, so "professorize this" inside a longer sentence should
    still fire. Fuzzy overlap is the fallback for imperfect recognition.
    """
    shortcuts = _all(conn)
    if not shortcuts:
        return None

    key = normalise_key(said)
    scored = []
    for s in shortcuts:
        trig = s["trigger"]
        if not trig:
            continue
        verbatim = trig in key
        if verbatim:
            score = 1.0
        else:
            head = _head_similarity(said, trig)
            # The head gate comes first. Without it, whole-phrase similarity
            # lets an unrelated request through on shared filler words.
            score = max(head, _window_similarity(key, trig)) if head >= TRIGGER_FLOOR else head
        scored.append({**s, "score": round(score, 4), "verbatim": verbatim})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[0]
    runner = scored[1] if len(scored) > 1 else None

    if trace:
        trace.step("shortcut_lookup", floor=TRIGGER_FLOOR,
                   candidates=[{"phrase": s["phrase"], "score": s["score"],
                                "verbatim": s["verbatim"]} for s in scored[:4]])

    if top["score"] < TRIGGER_FLOOR:
        return None                                       # not a shortcut

    near = (runner and runner["score"] >= TRIGGER_FLOOR
            and (top["score"] - runner["score"]) < COLLISION_MARGIN)

    if near:
        _record_collision(conn, said, top["id"], runner["id"], top["score"] - runner["score"])
        if trace:
            trace.step("shortcut_near_miss", between=[top["phrase"], runner["phrase"]],
                       margin=round(top["score"] - runner["score"], 4),
                       top_verbatim=top["verbatim"])

        # If exactly one of them was said word for word, that is real evidence
        # and Kivi proceeds — but it records the near miss, so the interface can
        # say "these two keep getting confused, rename one" instead of the
        # person discovering it from a message they already sent.
        if not (top["verbatim"] and not runner["verbatim"]):
            return {
                "status": "ambiguous_trigger",
                "say": f"“{top['phrase']}” and “{runner['phrase']}” sound alike. Which did you mean?",
                "options": [top["phrase"], runner["phrase"]],
                "field": "shortcut",
                "candidates": [top, runner],
            }

    # Scope.
    if top["apps"] and app and app not in top["apps"]:
        if trace:
            trace.step("shortcut_out_of_scope", phrase=top["phrase"],
                       allowed=top["apps"], here=app)
        return {
            "status": "out_of_scope",
            "say": f"“{top['phrase']}” is set up for {', '.join(top['apps'])}, not {app}.",
            "options": ["use it here anyway", "leave it alone"],
            "shortcut": top,
        }

    if top["fires_on"] == "selection" and not has_selection:
        if trace:
            trace.step("shortcut_needs_selection", phrase=top["phrase"])
        return {
            "status": "needs_selection",
            "say": f"Select the text you want “{top['phrase']}” applied to.",
            "field": "selection",
            "shortcut": top,
        }

    if trace:
        trace.step("shortcut_matched", phrase=top["phrase"], score=top["score"],
                   verbatim=top["verbatim"], applies=top["understood"],
                   not_executable=top["not_executable"])
    out = {"status": "matched", "shortcut": top, "score": top["score"]}
    if near:
        out["near_miss"] = {"against": runner["phrase"], "against_id": runner["id"],
                            "margin": round(top["score"] - runner["score"], 4)}
    return out


def _record_collision(conn: sqlite3.Connection, said: str, chosen: str,
                      against: str, margin: float) -> None:
    conn.execute(
        """INSERT INTO shortcut_collision (ts, said, chosen, against, margin)
           VALUES (?,?,?,?,?)""",
        (now(), said, chosen, against, round(margin, 4)),
    )
    conn.commit()


def collisions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Unresolved near-misses, newest first, for the interface to surface."""
    rows = conn.execute(
        """SELECT c.*, a.body AS chosen_body, b.body AS against_body
           FROM shortcut_collision c
           LEFT JOIN memory a ON a.id = c.chosen
           LEFT JOIN memory b ON b.id = c.against
           WHERE c.resolved = 0 ORDER BY c.ts DESC LIMIT 10"""
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "said": r["said"], "margin": r["margin"],
            "chosen": r["chosen"], "against": r["against"],
            "chosen_body": r["chosen_body"], "against_body": r["against_body"],
        })
    return out


def collision_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """SELECT chosen, COUNT(*) n FROM shortcut_collision
           WHERE resolved = 0 GROUP BY chosen"""
    ).fetchall()
    return {r["chosen"]: r["n"] for r in rows}


def rename(conn: sqlite3.Connection, memory_id: str, phrase: str) -> dict[str, Any]:
    """Rename a trigger and clear the collisions it was involved in."""
    row = conn.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone()
    if not row:
        return {"error": "no such shortcut"}
    payload = jload(row["payload"])
    payload["phrase"] = phrase
    trigger = normalise_key(phrase)
    payload["trigger"] = trigger
    conn.execute(
        "UPDATE memory SET subject=?, payload=?, updated_ts=? WHERE id=?",
        (trigger, jdump(payload), now(), memory_id),
    )
    conn.execute(
        "UPDATE shortcut_collision SET resolved=1 WHERE chosen=? OR against=?",
        (memory_id, memory_id),
    )
    conn.execute(
        "INSERT INTO memory_event (memory_id, ts, event, detail) VALUES (?,?,?,?)",
        (memory_id, now(), "edited", f"renamed to “{phrase}”"),
    )
    conn.commit()
    return {"status": "renamed", "id": memory_id, "phrase": phrase, "trigger": trigger}


def install_from_record(conn: sqlite3.Connection, record: dict[str, Any]) -> dict | None:
    """Restore a shortcut the person taught and confirmed in the past.

    Used only when loading history. It is not a way around the confirmation
    step: `meta.taught_shortcut` means "this person already reviewed and saved
    this definition", which is exactly what a seeded account should contain.
    Live teaching still goes through interpret-then-save.
    """
    spec = (record.get("meta") or {}).get("taught_shortcut")
    if not spec or not spec.get("phrase"):
        return None
    draft = interpret(spec["phrase"], spec.get("meaning", ""),
                      apps=spec.get("apps") or [],
                      fires_on=spec.get("fires_on", "selection"))
    return save(conn, draft, utt_id=record.get("id"))


def listing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    counts = collision_counts(conn)
    out = []
    for s in _all(conn):
        out.append({**s, "collisions": counts.get(s["id"], 0)})
    return out
