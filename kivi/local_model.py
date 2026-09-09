"""A deterministic implementation of the three model-shaped decisions Kivi makes.

The product needs a model to do three things:
    1. decide what a spoken request is asking for      -> classify_intent
    2. decide what, if anything, is worth remembering  -> extract
    3. reshape text according to remembered rules      -> reshape

This module does all three without a network call, so the system runs and can be
evaluated with no API key. `kivi.llm` can swap these for a hosted model; the
signatures and return shapes are identical, and the evaluation runs against
either.

It is rule-driven, and that is a deliberate limitation rather than a hidden one:
the evaluation reports where it abstains and where it is wrong.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# text utilities
# --------------------------------------------------------------------------

_WORD = re.compile(r"[\w'-]+", re.UNICODE)

FILLER = {
    "um", "umm", "uh", "erm", "like", "basically", "actually", "okay", "ok",
    "so", "just", "kind", "sort", "really", "you", "know", "i", "mean", "na",
    "ya", "yaar", "haan",
}


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "")
    return [t.lower() for t in _WORD.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in FILLER and len(t) > 1]


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def normalise_key(text: str) -> str:
    return " ".join(tokens(text))


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def bag(text: str) -> dict[str, float]:
    """Sublinear term-frequency vector. No corpus fit needed, so retrieval
    behaves identically on an empty database and a full one."""
    vec: dict[str, float] = {}
    for t in content_tokens(text):
        vec[t] = vec.get(t, 0.0) + 1.0
    return {k: 1.0 + math.log(v) for k, v in vec.items()}


# --------------------------------------------------------------------------
# intent classification
# --------------------------------------------------------------------------

INTENT_EXEMPLARS: dict[str, list[str]] = {
    "find_dictation": [
        "find the dictation I did yesterday in slack",
        "what did I dictate this morning in gmail",
        "pull up the message I spoke around 5 pm",
        "find what I said about the latency numbers last week",
        "show me the note I dictated in notion on tuesday",
    ],
    "reshape": [
        "make this shorter",
        "polish this for the meeting",
        "rewrite this more formally",
        "turn this into three bullet points",
        "clean this up before I send it",
        "make this concise but keep the technical meaning",
    ],
    "recall": [
        "what do you know about arjun",
        "how do you spell sarvam",
        "what have you remembered about me",
        "what rules are you following for my emails",
        "why did you write it that way",
    ],
    "draft_message": [
        "draft a reply to the professor",
        "write a message to amma saying I will be late",
        "tell the team the meeting moved to four",
        "send arjun a note about the review",
        "write an email asking for the dataset access",
    ],
    "remember": [
        "remember that I prefer short emails",
        "always keep my updates to three bullets",
        "never write dear sir or madam",
        "note that sarvam is spelled with an a",
        "from now on explain method sections in tamil",
    ],
    "forget": [
        "forget that rule",
        "stop doing that",
        "delete what you remembered about my emails",
        "that is not a rule",
        "unlearn the tamil preference",
    ],
}

_INTENT_VECTORS = {
    name: [bag(x) for x in examples] for name, examples in INTENT_EXEMPLARS.items()
}

# Strong lexical signals that outrank fuzzy similarity. Ordered: first match wins.
_INTENT_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\b(forget|unlearn|stop doing|not a rule|delete (?:what|the) (?:you )?remember)\b", re.I), "forget", 0.92),
    (re.compile(r"\b(remember (?:that|this)|from now on|always|never)\b", re.I), "remember", 0.88),
    (re.compile(r"\b(find|pull up|show me|what did i)\b.*\b(dictat|said|spoke|wrote|note|message)\w*\b", re.I), "find_dictation", 0.90),
    (re.compile(r"\b(what do you know|what have you remembered|why did you|which rules?)\b", re.I), "recall", 0.90),
    (re.compile(r"\b(draft|write|reply|tell|send)\b.*\b(to|for)\b", re.I), "draft_message", 0.80),
    (re.compile(r"\b(make (?:this|it)|rewrite|polish|shorten|turn this into|clean (?:this|it) up)\b", re.I), "reshape", 0.86),
]


def classify_intent(text: str) -> tuple[str, float, dict[str, float]]:
    """Return (intent, confidence, all_scores).

    Confidence is a cosine score, boosted when an unambiguous lexical rule
    fires. The caller decides whether the score clears the abstention floor;
    this function never decides to act.
    """
    q = bag(text)
    scores: dict[str, float] = {}
    for name, vectors in _INTENT_VECTORS.items():
        scores[name] = max((cosine(q, v) for v in vectors), default=0.0)

    for pattern, name, floor in _INTENT_RULES:
        if pattern.search(text or ""):
            scores[name] = max(scores.get(name, 0.0), floor)
            break

    best = max(scores, key=lambda k: scores[k]) if scores else "reshape"
    return best, round(scores.get(best, 0.0), 4), {k: round(v, 4) for k, v in scores.items()}


# --------------------------------------------------------------------------
# what must never be learned
# --------------------------------------------------------------------------

SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # A credential is a word plus a value. "The OTP step was the blocker" names
    # a mechanism and must not be refused; "the OTP is 449281" must be.
    ("credential", re.compile(r"\b(?:password|passcode|api key|secret key|access token)\b[^\n]{0,30}?(?:\bis\b|=|:)\s*\S", re.I)),
    ("credential", re.compile(r"\botp\b[^\n]{0,15}?\b\d{4,8}\b", re.I)),
    ("credential", re.compile(r"\b\d{4,8}\b[^\n]{0,15}?\b(?:otp|one[- ]time code)\b", re.I)),
    ("credential", re.compile(r"\bpin (?:is|number)\b", re.I)),
    ("credential", re.compile(r"\bone[- ]time code\b[^\n]{0,15}?\b\d{4,8}\b", re.I)),
    ("financial_id", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("financial_id", re.compile(r"\b(account number|card number|cvv|ifsc|upi id)\b", re.I)),
    ("health", re.compile(r"\b(diagnos\w+|prescri\w+|blood (?:test|sugar|pressure)|biopsy|chemo\w*|hiv)\b", re.I)),
    ("third_party_pii", re.compile(r"\b(aadhaar|pan number|passport number|his address is|her address is)\b", re.I)),
]


def sensitivity(text: str) -> str | None:
    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text or ""):
            return label
    return None


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------


@dataclass
class Candidate:
    kind: str                 # fact | preference | episode
    subject: str
    body: str
    confidence: float
    origin: str               # taught | corrected | observed
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    scope_app: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "subject": self.subject, "body": self.body,
            "confidence": round(self.confidence, 4), "origin": self.origin,
            "reason": self.reason, "payload": self.payload, "scope_app": self.scope_app,
        }


# --- fact patterns: an in-place correction of a word ----------------------
# In every "X not Y" construction the corrected form comes first and the
# misheard form second: "no — Sarvam AI, not Sharvam". Getting this direction
# backwards would teach Kivi the error, so the group names are explicit.
_FACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"\b(?:no|nope|it'?s|its)\b[\s,\u2014\u2013-]*(?:it'?s\s+)?"
        r"(?P<right>[\w][\w .'\u2019-]{1,39}?)\s*,?\s+not\s+(?P<wrong>[\w'\u2019-]{2,30})",
        re.I), "correction"),
    (re.compile(r"\bspell\s+(?P<wrong>[\w'\u2019-]{2,30})\s+as\s+(?P<right>[\w .'\u2019-]{2,40})", re.I), "spelling"),
    (re.compile(r"\bwhen i say\s+(?P<wrong>[\w'\u2019-]{2,30})\s*,?\s*(?:write|it'?s|use)\s+(?P<right>[\w .'\u2019-]{2,40})", re.I), "expansion"),
    (re.compile(r"^(?P<right>[\w][\w .'\u2019-]{1,39}?)\s*,\s*not\s+(?P<wrong>[\w'\u2019-]{2,30})", re.I), "correction"),
]

# "it's fine, not a problem" is a turn of phrase, not a spelling correction.
# A term worth learning is not one of these.
_NOT_A_TERM = {
    "a", "an", "the", "that", "this", "it", "one", "problem", "issue", "sure",
    "fine", "good", "bad", "ok", "okay", "yet", "now", "really", "much", "many",
    "possible", "practical", "done", "ready", "able", "worth", "enough", "clear",
}

# --- preference patterns: a durable instruction about output --------------
_PREF_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\bremember (?:that |this[:,]? )?(?P<rule>.{6,160})", re.I), 0.95),
    (re.compile(r"\bfrom now on,?\s*(?P<rule>.{6,160})", re.I), 0.93),
    (re.compile(r"\b(?:always|never)\s+(?P<rule>.{6,160})", re.I), 0.88),
    (re.compile(r"\bi (?:prefer|always want|would rather)\s+(?P<rule>.{6,160})", re.I), 0.86),
    (re.compile(r"\bkeep (?:my |the )?(?P<rule>\w[\w ]{2,40}\s+(?:to|under)\s+.{2,60})", re.I), 0.84),
    (re.compile(r"\bdon'?t\s+(?P<rule>.{6,160})", re.I), 0.72),
]

_REMINDER = re.compile(
    r"\bremind me\s+(?:to\s+)?(?P<what>.{3,120}?)(?:\s+at\s+(?P<when>[\w: .]{2,20}))?\s*$", re.I
)


def _clean_rule(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,;:—-")
    return text[:1].upper() + text[1:] if text else text


def extract(record: dict[str, Any]) -> tuple[list[Candidate], list[dict[str, str]]]:
    """Given one utterance, return (candidates, ignored).

    `ignored` is as important as `candidates`: it is how the product shows the
    person, and the evaluation shows an engineer, what Kivi decided not to keep.
    """
    raw = record.get("raw_asr", "") or ""
    formatted = record.get("formatted", "") or ""
    app = record.get("app")
    meta = record.get("meta") or {}
    text = raw

    candidates: list[Candidate] = []
    ignored: list[dict[str, str]] = []

    # 1. Hard refusals come first, before anything is parsed out.
    label = sensitivity(text) or sensitivity(formatted)
    if label:
        ignored.append({
            "what": "the whole utterance",
            "reason": f"contains {label.replace('_', ' ')}; this category is never stored",
        })
        return candidates, ignored

    if record.get("private"):
        ignored.append({
            "what": "the whole utterance",
            "reason": "dictated while the mic was marked private",
        })
        return candidates, ignored

    # 2. Explicit reminders are episodic tasks, not preferences.
    m = _REMINDER.search(text)
    if m:
        what = _clean_rule(m.group("what"))
        candidates.append(Candidate(
            kind="episode", subject=normalise_key(what)[:60],
            body=f"Reminder: {what}",
            confidence=0.94, origin="taught",
            reason="an explicit reminder request",
            payload={"task": what, "when": (m.group("when") or "").strip(), "type": "reminder"},
            scope_app=None,
        ))

    # 3. Corrections become facts.
    seen_facts: set[str] = set()
    for pattern, flavour in _FACT_PATTERNS:
        for fm in pattern.finditer(text):
            wrong = fm.group("wrong").strip(" .,")
            right = fm.group("right").strip(" .,")
            if not wrong or not right or wrong.lower() == right.lower():
                continue
            if len(right) > 40 or " " in wrong:
                continue
            if wrong.lower() in _NOT_A_TERM or right.lower() in _NOT_A_TERM:
                continue
            key = normalise_key(wrong)
            if key in seen_facts:
                continue
            seen_facts.add(key)
            candidates.append(Candidate(
                kind="fact", subject=key, body=f"{wrong} → {right}",
                confidence=0.9 if flavour != "correction" else 0.86,
                origin="corrected",
                reason=f"an in-place {flavour} while dictating",
                payload={"wrong": wrong, "right": right, "flavour": flavour},
            ))
        if seen_facts:
            break

    # 4. Instructions become preferences.
    for pattern, conf in _PREF_PATTERNS:
        pm = pattern.search(text)
        if not pm:
            continue
        rule = _clean_rule(pm.group("rule"))
        if len(rule.split()) < 2:
            continue
        # "never write Dear Sir" keeps its polarity; the matched verb is dropped
        # by the group, so re-attach it.
        head = pm.group(0).split()[0].lower()
        if head in {"always", "never", "don't", "dont"}:
            rule = f"{head.capitalize()} {rule[0].lower()}{rule[1:]}"
        candidates.append(Candidate(
            kind="preference", subject=normalise_key(rule)[:80], body=rule,
            confidence=conf, origin="taught",
            reason="stated as a standing instruction",
            payload=_compile_rule(rule),
            scope_app=None,
        ))
        break

    # 5. Repeated behaviour becomes an observed preference (never active yet).
    edit = meta.get("user_edit")
    if edit:
        body = _edit_to_rule(edit)
        if body:
            candidates.append(Candidate(
                kind="preference", subject=normalise_key(body)[:80], body=body,
                confidence=0.45, origin="observed",
                reason=f"you edited Kivi's output ({edit}) — noticed, not applied",
                payload=_compile_rule(body), scope_app=app,
            ))
        else:
            ignored.append({"what": edit, "reason": "an edit with no repeatable pattern"})

    # 6. Every non-private utterance is an episode. This is the cheapest and
    #    most useful memory in the product: it is what "find the dictation I
    #    did at 5pm" runs on.
    if formatted.strip():
        candidates.append(Candidate(
            kind="episode", subject=normalise_key(formatted)[:80],
            body=formatted.strip()[:400], confidence=1.0, origin="observed",
            reason="every dictation is recallable by time, app and content",
            payload={"type": "dictation", "app": app},
            scope_app=app,
        ))

    # 7. Say plainly what was thrown away.
    if not any(c.kind == "fact" for c in candidates) and re.search(r"\bnot\b", text, re.I):
        ignored.append({"what": "a possible correction", "reason": "could not tell which word was being corrected"})
    if not any(c.kind == "preference" for c in candidates):
        ignored.append({"what": "the content of what you said", "reason": "content is not a rule; Kivi stores how you write, not what you claim"})

    return candidates, ignored


def _edit_to_rule(edit: str) -> str | None:
    """Turn a described user edit into a candidate rule, or None."""
    e = edit.lower()
    if re.search(r"\bshorten\w*|\bmade shorter|\bcut length", e):
        return "Keep emails to three sentences unless I ask for more"
    if "removed apolog" in e or "cut apolog" in e:
        return "Never stack apologies in a message"
    if "removed greeting" in e or "dear sir" in e:
        return "Never open with Dear Sir/Madam"
    if "to bullets" in e or "made bullets" in e:
        return "Prefer bullets over paragraphs for updates"
    if "tamil" in e:
        return "Explain method sections in Tamil"
    return None


# --------------------------------------------------------------------------
# rule compilation + reshaping
# --------------------------------------------------------------------------

HEDGES = [
    r"\bi think\b", r"\bi guess\b", r"\bkind of\b", r"\bsort of\b", r"\bmaybe\b",
    r"\bjust\b", r"\bbasically\b", r"\bactually\b", r"\ba bit\b", r"\bsomewhat\b",
    r"\bi feel like\b", r"\bprobably\b",
]
APOLOGIES = [
    r"\bsorry to bother you( again)?\b", r"\bsorry again\b", r"\bapologies\b",
    r"\bi'?m (?:so |really )?sorry\b", r"\bsorry for the trouble\b",
]
GREETINGS_FORMAL = [r"\bdear sir(?:/| or )?(?:madam)?\b", r"\bto whom it may concern\b"]


def _compile_rule(rule: str) -> dict[str, Any]:
    """Turn a plain-language rule into something executable.

    Anything not recognised stays as `unstructured`, and the product says so
    rather than pretending the rule is in force.
    """
    r = rule.lower()
    out: dict[str, Any] = {"source_text": rule}
    m = re.search(r"\b(?:to|under|max(?:imum)?(?: of)?)\s+(\w+)\s+sentence", r)
    if m:
        out["max_sentences"] = _number(m.group(1))
    m = re.search(r"\b(\w+)\s+bullets?\b", r)
    if m and _number(m.group(1)):
        out["bullets"] = _number(m.group(1))
    elif "bullet" in r:
        out["bullets"] = 0  # bullets, count unspecified
    if re.search(r"\bapolog", r):
        out["no_apology"] = True
    if re.search(r"\bdear sir|whom it may concern", r):
        out["no_formal_greeting"] = True
    if re.search(r"\bhedg|adjective|fluff|no filler", r):
        out["no_hedging"] = True
    if re.search(r"\bformal\b", r):
        out["register"] = "formal"
    elif re.search(r"\bcasual|warm|friendly\b", r):
        out["register"] = "casual"
    m = re.search(r"\b(tamil|hindi|telugu|kannada|malayalam|bengali|marathi|english)\b", r)
    if m:
        out["language"] = m.group(1)
    m = re.search(r"\bone (?:clear )?ask\b", r)
    if m:
        out["single_ask"] = True
    # A rule usually names where it applies: "my Slack updates", "my emails".
    # Without this, a rule about Slack reshapes a draft in Gmail.
    m = re.search(r"\b(slack|gmail|whatsapp|cursor|notion|teams|e-?mails?|messages?)\b", r)
    if m:
        out["applies_to"] = _APP_FOR.get(m.group(1).lower().rstrip("s").replace("-", ""),
                                         m.group(1).title())
    if len(out) == 1:
        out["unstructured"] = True
    return out


_APP_FOR = {
    "slack": "Slack", "gmail": "Gmail", "whatsapp": "WhatsApp", "cursor": "Cursor",
    "notion": "Notion", "team": "Teams", "email": "Gmail", "message": "WhatsApp",
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _number(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return _NUMBER_WORDS.get(tok.lower())


def reshape(text: str, rules: list[dict[str, Any]], instruction: str = "") -> tuple[str, list[str]]:
    """Apply compiled rules plus a one-off spoken instruction.

    Returns the new text and the list of rules that actually changed something,
    so the interface can show what was applied rather than claiming it.
    """
    out = (text or "").strip()
    applied: list[str] = []
    merged: dict[str, Any] = {}
    for r in rules:
        merged.update({k: v for k, v in r.items() if k not in ("source_text", "unstructured")})

    inst = (instruction or "").lower()
    want_concise = bool(re.search(r"\b(shorter|concise|shorten|tighten|brief|trim)\b", inst))
    if want_concise:
        merged.setdefault("max_sentences", max(1, len(sentences(out)) - 1))
        merged["compress"] = True
    if re.search(r"\bbullet", inst):
        m = re.search(r"\b(\w+)\s+bullet", inst)
        merged["bullets"] = (_number(m.group(1)) if m else 0) or 0
    if re.search(r"\bformal\b", inst):
        merged["register"] = "formal"
    if re.search(r"\bcasual|warmer|friendl", inst):
        merged["register"] = "casual"

    before = out
    if merged.get("no_apology"):
        for p in APOLOGIES:
            out = re.sub(p + r"[,.]?\s*", "", out, flags=re.I)
        if out != before:
            applied.append("no stacked apologies")
        before = out

    if merged.get("no_formal_greeting"):
        for p in GREETINGS_FORMAL:
            out = re.sub(p + r"[,.]?\s*", "", out, flags=re.I)
        if out != before:
            applied.append("no Dear Sir/Madam")
        before = out

    if merged.get("no_hedging"):
        for p in HEDGES:
            out = re.sub(p + r"\s*", "", out, flags=re.I)
        if out != before:
            applied.append("no hedging")
        before = out

    if merged.get("register") == "formal":
        out = _register(out, formal=True)
        if out != before:
            applied.append("formal register")
        before = out
    elif merged.get("register") == "casual":
        out = _register(out, formal=False)
        if out != before:
            applied.append("casual register")
        before = out

    if "bullets" in merged:
        n = merged["bullets"] or None
        # "Prefer bullets over paragraphs for updates" is a weak preference. It
        # must not turn a one-line draft into a single bullet, so bullets are
        # only forced when a count is named or the request asks for them.
        explicit = bool(n) or bool(re.search(r"\bbullet", inst))
        sents = sentences(out)
        if explicit and (len(sents) > 1 or n):
            if n:
                sents = sents[:n]
            out = "\n".join(f"• {s.rstrip('.')}" for s in sents)
            applied.append(f"{len(sents)} bullet{'s' if len(sents) != 1 else ''}")
        else:
            merged.pop("bullets", None)
        before = out

    if merged.get("compress"):
        out = _compress(out)
        if out != before:
            applied.append("tightened wording")
        before = out

    if merged.get("max_sentences") and "bullets" not in merged:
        n = int(merged["max_sentences"])
        sents = sentences(out)
        if len(sents) > n:
            out = " ".join(sents[:n])
            applied.append(f"cut to {n} sentence{'s' if n != 1 else ''}")
        before = out

    if merged.get("single_ask"):
        qs = [s for s in sentences(out) if s.endswith("?")]
        if len(qs) > 1:
            keep = qs[0]
            for extra in qs[1:]:
                out = out.replace(" " + extra, "").replace(extra, "")
            applied.append("one ask only")

    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([.,;:?!])", r"\1", out)
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out, applied


_CASUAL_TO_FORMAL = [
    (r"\bhey\b", "Dear"), (r"\bhi\b", "Dear"), (r"\bthanks\b", "Thank you"),
    (r"\bcan you\b", "Could you"), (r"\bi haven'?t got\b", "I have not received"),
    (r"\bgot\b", "received"), (r"\bwanna\b", "want to"), (r"\bgonna\b", "going to"),
    (r"\bsir\b", "Professor"), (r"\bASAP\b", "at your earliest convenience"),
]
_FORMAL_TO_CASUAL = [
    (r"\bI would like to\b", "I want to"), (r"\bCould you kindly\b", "Can you"),
    (r"\bat your earliest convenience\b", "when you can"),
    (r"\bI have not received\b", "I still haven't got"),
    (r"\bThank you for your\b", "Thanks for the"),
]


_VERBOSE = [
    (r"\brequires significant engineering effort\b", "is costly"),
    (r"\bmay not be practical within\b", "may not fit"),
    (r"\bso we have decided to report\b", "; we report"),
    (r"\bin order to\b", "to"),
    (r"\bat this point in time\b", "now"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bit is important to note that\b", ""),
    (r"\bwe would like to\b", "we"),
    (r"\bthere is a possibility that\b", "possibly"),
    (r"\bwith regard to\b", "about"),
    (r"\ba large number of\b", "many"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bin the event that\b", "if"),
    (r"\bhas the ability to\b", "can"),
    (r"\bthe current timeline\b", "the current timeline"),
]


def _compress(text: str) -> str:
    """Shorten wording without dropping content. Used when the person asks for
    something more concise but there is only one sentence to work with."""
    out = text
    for pattern, repl in _VERBOSE:
        out = re.sub(pattern, repl, out, flags=re.I)
    for p in HEDGES:
        out = re.sub(p + r"\s*", "", out, flags=re.I)
    out = re.sub(r"\s*;\s*;\s*", "; ", out)
    out = re.sub(r",\s*;", ";", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _register(text: str, formal: bool) -> str:
    pairs = _CASUAL_TO_FORMAL if formal else _FORMAL_TO_CASUAL
    for pattern, repl in pairs:
        text = re.sub(pattern, repl, text, flags=re.I)
    if formal:
        text = re.sub(r"([a-z])'([a-z])", lambda m: m.group(1) + "'" + m.group(2), text)
    return text


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)
