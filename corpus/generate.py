#!/usr/bin/env python3
"""Build the development corpus.

~500 transcript-like records. Each has raw recogniser output, the formatted
text Kivi wrote into the app, and the metadata this product actually needs:
app, time, language mix, privacy flag, and any edit the person made afterwards.

Every record carries an `expect` block — the ground truth the evaluation scores
against. That is the point of generating rather than scraping: without labels
you can measure that the system runs, not that it is right.

Synthesis is template-and-slot with a fixed seed, so `python corpus/generate.py`
reproduces the file byte for byte. It is not LLM-generated: the corpus has to be
independent of the model being evaluated, or the evaluation measures agreement
with itself. Variety comes from 60+ templates crossed with slot values,
disfluency injection, and code-mixing.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "corpus" / "corpus.jsonl"

SEED = 20260905
TARGET = 500

APPS = ["Slack", "Gmail", "WhatsApp", "Cursor", "Notion", "Docs", "Chrome", "Teams"]
APP_WEIGHTS = [0.24, 0.18, 0.16, 0.14, 0.10, 0.08, 0.06, 0.04]

FILLERS = ["um", "uh", "so", "okay so", "like", "I mean", "basically", "na"]
NAMES = ["Arjun", "Rahul", "Priya", "Meera", "Vikram", "Kavya", "Raman"]

# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

# 1. Ordinary dictation. Nothing to learn but the episode itself.
PLAIN = [
    ("the auth flow is done, {name} should review it before standup",
     "The auth flow is done. {name} should review it before standup."),
    ("tell the team latency numbers will land tomorrow morning",
     "Latency numbers will land tomorrow morning."),
    ("I'll fold the results into the deck before the review",
     "I'll fold the results into the deck before the review."),
    ("the third seed finished overnight, variance is smaller than we thought",
     "The third seed finished overnight; variance is smaller than we thought."),
    ("can we move the vendor call to four instead of three",
     "Can we move the vendor call to 4 instead of 3?"),
    ("the decoder is conditioned on a language agnostic representation",
     "The decoder is conditioned on a language-agnostic representation."),
    ("I pushed the fix for the empty input crash",
     "I pushed the fix for the empty-input crash."),
    ("reviewing the preprint now, section four is the weak part",
     "Reviewing the preprint now. Section 4 is the weak part."),
    ("dinner ku vandhuduven, meeting konjam late aagum",
     "Dinner-ku vandhuduven, meeting konjam late aagum."),
    ("kal subah tak numbers bhej dunga",
     "Kal subah tak numbers bhej dunga."),
    ("add a retry on the 401 but keep the session token unchanged",
     "Add a retry on the 401, but keep sessionToken unchanged."),
    ("the ablation shows the biggest gain on utterances with two switch points",
     "The ablation shows the biggest gain on utterances with two switch points."),
    ("I'm not able to attend Friday, there's a family function",
     "I won't be able to attend Friday — I have a family commitment."),
    ("shared the tracker with design and engineering both",
     "Shared the tracker with design and engineering."),
    ("the OTP step was the block in onboarding, drop off was thirty eight percent",
     "The OTP step was the block in onboarding; drop-off was 38%."),
    ("let's ship the prototype before the research review",
     "Let's ship the prototype before the research review."),
    ("I rewrote the cutover plan and split it across three people",
     "I rewrote the cutover plan and split it across three people."),
    ("duplicate tickets dropped to almost none within a month",
     "Duplicate tickets dropped to almost none within a month."),
    ("naan innaikku late-ah varuven, appuram call pannuren",
     "Naan innaikku late-ah varuven, appuram call pannuren."),
    ("check whether the encoder handles more than two switch points",
     "Check whether the encoder handles more than two switch points."),
]

# 2. In-place corrections. These must become facts.
CORRECTIONS = [
    ("no — Sarvam AI, not Sharvam", "Sarvam AI", ("sharvam", "Sarvam AI")),
    ("it's Arjun, not Arjuna", "Arjun", ("arjuna", "Arjun")),
    ("spell Kavya as Kaavya", "Kaavya", ("kavya", "Kaavya")),
    ("no, Saaras not Sarah's", "Saaras", ("sarah's", "Saaras")),
    ("when I say ASR, write speech recognition", "ASR", ("asr", "speech recognition")),
    ("it's Meera, not Mira", "Meera", ("mira", "Meera")),
    ("no — Bulbul, not Bulbull", "Bulbul", ("bulbull", "Bulbul")),
    ("spell sem as semester", "semester", ("sem", "semester")),
    ("it's Tanglish, not Tamlish", "Tanglish", ("tamlish", "Tanglish")),
    ("no, Saaras not Sarus", "Saaras", ("sarus", "Saaras")),
]

# 3. Explicit standing instructions. These must become active preferences.
INSTRUCTIONS = [
    "remember that I keep emails to three sentences",
    "from now on never write Dear Sir or Madam",
    "always put the number first in a status update",
    "I prefer bullets over paragraphs for updates",
    "remember to explain method sections in Tamil",
    "always keep my Slack updates to three bullets",
    "I prefer formal wording when I write to the professor",
    "from now on no hedging in my written answers",
    "remember that I want one clear ask per email",
]

# 4. Behaviour Kivi can notice but must not act on until it repeats.
EDITS = [
    ("shortened by about a third", "Keep emails to three sentences unless I ask for more"),
    ("removed apologies", "Never stack apologies in a message"),
    ("removed greeting Dear Sir", "Never open with Dear Sir/Madam"),
    ("rewrote to bullets", "Prefer bullets over paragraphs for updates"),
]

# 5. Categories that must be refused outright.
SENSITIVE = [
    ("the OTP is 449281, use it before it expires", "credential"),
    ("my password for the portal is kivi@2026", "credential"),
    ("card number 4539 8821 0043 7712 for the booking", "financial_id"),
    ("the API key is sk-live-9f2b, keep it somewhere", "credential"),
    ("her blood pressure reading was high again this week", "health"),
    ("the doctor changed my prescription yesterday", "health"),
    ("his Aadhaar number is on the form already", "third_party_pii"),
    ("account number ending 4471, IFSC on the invoice", "financial_id"),
]

# 6. Reminders — episodic tasks, not preferences.
REMINDERS = [
    "remind me to tell {name} about the event at 9 PM",
    "remind me to send the deck at 6",
    "remind me to follow up with {name} tomorrow",
    "remind me to check the third seed at 11 PM",
]

# 7. Requests Kivi should not be able to resolve without asking.
AMBIGUOUS = [
    "send this to him",
    "do that thing again",
    "make it like the other one",
    "fix this the usual way",
]


def disfluent(text: str, rng: random.Random) -> str:
    """Add the noise a recogniser actually returns."""
    words = text.split()
    if len(words) > 6 and rng.random() < 0.55:
        pos = rng.randrange(1, min(6, len(words)))
        words.insert(pos, rng.choice(FILLERS))
    if len(words) > 8 and rng.random() < 0.3:
        pos = rng.randrange(2, len(words) - 2)
        words.insert(pos + 1, words[pos])  # stutter
    out = " ".join(words)
    if rng.random() < 0.35:
        out = out.lower()
    return out


def languages_for(text: str) -> list[str]:
    tam = any(w in text.lower() for w in
              ("aagum", "vandhuduven", "varuven", "pannuren", "-ku", "-kitta", "naan", "innaikku"))
    hin = any(w in text.lower() for w in ("kal", "subah", "bhej", "dunga", "mera", "hai"))
    langs = ["en"]
    if tam:
        langs = ["ta", "en"]
    elif hin:
        langs = ["hi", "en"]
    return langs


def build() -> list[dict]:
    rng = random.Random(SEED)
    now = datetime(2026, 9, 5, 9, 0, 0)
    records: list[dict] = []

    def stamp(days_ago: int, hour: int, minute: int | None = None) -> float:
        d = (now - timedelta(days=days_ago)).replace(
            hour=hour, minute=minute if minute is not None else rng.randrange(0, 60),
            second=rng.randrange(0, 60), microsecond=0,
        )
        return d.timestamp()

    def add(raw, formatted, app, days, hour, expect, minute=None, private=False, meta=None):
        idx = len(records)
        ts = stamp(days, hour, minute)
        records.append({
            "id": f"utt_{idx:04d}",
            "ts": ts,
            # The moment the corpus was generated. The loader shifts every
            # record forward by a whole number of days from here, so "yesterday
            # at 5 PM" is still yesterday at 5 PM whenever the repository is
            # cloned. Whole days, not raw seconds, so the hour is preserved.
            "gen_ts": now.timestamp(),
            "app": app,
            "surface": "dictation",
            "raw_asr": raw,
            "formatted": formatted,
            "languages": languages_for(raw),
            "private": bool(private),
            "meta": meta or {},
            "expect": expect,
        })

    # --- anchors the evaluation depends on --------------------------------
    # The brief's example query: a Slack dictation around 5 PM yesterday.
    add("okay so quick update the third seed finished and the latency numbers are ready "
        "I think we should walk through them in the review",
        "Quick update: the third seed finished and the latency numbers are ready. "
        "I think we should walk through them in the review.",
        "Slack", 1, 17, {"kinds": ["episode"], "anchor": "slack_5pm_yesterday"}, minute=12)
    # A decoy at the same hour in a different app.
    add("the family lunch is on sunday, tell amma we will reach by noon",
        "The family lunch is on Sunday — tell Amma we'll reach by noon.",
        "WhatsApp", 1, 17, {"kinds": ["episode"], "anchor": "whatsapp_5pm_decoy"}, minute=20)
    # A decoy in the same app on a different day.
    add("pushing the router change now, review after standup",
        "Pushing the router change now. Review after standup.",
        "Slack", 3, 17, {"kinds": ["episode"], "anchor": "slack_5pm_wrong_day"}, minute=5)

    # --- corrections ------------------------------------------------------
    for i, (raw, _canon, (wrong, right)) in enumerate(CORRECTIONS):
        app = rng.choices(APPS, APP_WEIGHTS)[0]
        add(raw, raw, app, rng.randrange(1, 12), rng.randrange(9, 21),
            {"kinds": ["fact", "episode"], "fact": {"wrong": wrong, "right": right}})

    # --- explicit instructions -------------------------------------------
    for raw in INSTRUCTIONS:
        app = rng.choices(APPS, APP_WEIGHTS)[0]
        add(raw, raw, app, rng.randrange(1, 12), rng.randrange(9, 21),
            {"kinds": ["preference", "episode"], "preference_active": True})

    # --- repeated edits: three of each, so promotion is exercised ---------
    for edit_desc, rule in EDITS:
        for n in range(3):
            base = rng.choice(PLAIN)
            raw = disfluent(base[0].format(name=rng.choice(NAMES)), rng)
            add(raw, base[1].format(name=rng.choice(NAMES)), "Gmail",
                rng.randrange(1, 10), rng.randrange(9, 20),
                {"kinds": ["preference", "episode"], "preference_observed": rule,
                 "promotes_at": 3, "occurrence": n + 1},
                meta={"user_edit": edit_desc})

    # --- sensitive: must be refused --------------------------------------
    for raw, label in SENSITIVE:
        app = rng.choices(APPS, APP_WEIGHTS)[0]
        add(raw, raw, app, rng.randrange(1, 12), rng.randrange(9, 21),
            {"kinds": [], "refuse": label})

    # --- private mic ------------------------------------------------------
    for i in range(6):
        base = rng.choice(PLAIN)
        add(base[0].format(name=rng.choice(NAMES)), base[1].format(name=rng.choice(NAMES)),
            rng.choices(APPS, APP_WEIGHTS)[0], rng.randrange(1, 12), rng.randrange(9, 21),
            {"kinds": [], "refuse": "private"}, private=True)

    # --- reminders --------------------------------------------------------
    for tmpl in REMINDERS:
        raw = tmpl.format(name=rng.choice(NAMES))
        add(raw, raw, rng.choices(APPS, APP_WEIGHTS)[0],
            rng.randrange(1, 8), rng.randrange(9, 21),
            {"kinds": ["episode"], "reminder": True})

    # --- ambiguous --------------------------------------------------------
    for raw in AMBIGUOUS:
        add(raw, raw, rng.choices(APPS, APP_WEIGHTS)[0],
            rng.randrange(1, 8), rng.randrange(9, 21),
            {"kinds": ["episode"], "ambiguous": True})

    # --- bulk ordinary dictation to fill out the corpus -------------------
    while len(records) < TARGET:
        base = rng.choice(PLAIN)
        name = rng.choice(NAMES)
        raw = disfluent(base[0].format(name=name), rng)
        formatted = base[1].format(name=name)
        app = rng.choices(APPS, APP_WEIGHTS)[0]
        days, hour = rng.randrange(1, 15), rng.randrange(8, 23)
        # Keep the 5 PM Slack anchor the only Slack entry in its window
        # yesterday. Two near-identical candidates there is a real ambiguity
        # and Kivi would rightly ask which one you meant, but it would make the
        # documented walkthrough non-deterministic.
        while app == "Slack" and days == 1 and 16 <= hour <= 18:
            days, hour = rng.randrange(1, 15), rng.randrange(8, 23)
        add(raw, formatted, app, days, hour, {"kinds": ["episode"]})

    records.sort(key=lambda r: r["ts"])
    # `occurrence` must count sightings in the order the system will actually
    # see them, which is only known after the time sort.
    seen: dict[str, int] = {}
    for i, r in enumerate(records):
        r["id"] = f"utt_{i:04d}"
        rule = r["expect"].get("preference_observed")
        if rule:
            seen[rule] = seen.get(rule, 0) + 1
            r["expect"]["occurrence"] = seen[rule]
    return records


def main() -> int:
    records = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    kinds: dict[str, int] = {}
    for r in records:
        key = ",".join(r["expect"].get("kinds", [])) or "refused"
        kinds[key] = kinds.get(key, 0) + 1
    print(f"wrote {len(records)} records to {OUT}")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    langs: dict[str, int] = {}
    for r in records:
        langs[",".join(r["languages"])] = langs.get(",".join(r["languages"]), 0) + 1
    print("  languages:", dict(sorted(langs.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
