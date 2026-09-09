"""Configuration and policy constants.

Everything in POLICY is a product decision, not a tuning knob. Each one is
defended in README.md under "Decisions". They live here so an engineer can find
every behavioural threshold in one file.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("KIVI_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("KIVI_DB", DATA_DIR / "kivi.db"))
CORPUS_PATH = Path(os.environ.get("KIVI_CORPUS", ROOT / "corpus" / "corpus.jsonl"))

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Which model backend answers. "local" is a deterministic, dependency-free
# implementation so the system runs with no API key. "anthropic" swaps in a
# hosted model for the same three call sites (classify, extract, reshape).
LLM_BACKEND = os.environ.get("KIVI_LLM", "local")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("KIVI_MODEL", "claude-sonnet-4-6")

POLICY = {
    # --- What memory is allowed to touch -------------------------------
    # Plain dictation reads facts only. A fact is a spelling, never a rewrite.
    # Preferences and episodes are Hey Kivi's alone. This is the central
    # boundary of the product.
    "dictation_reads": ("fact",),
    "heykivi_reads": ("fact", "preference", "episode"),

    # --- Promotion ------------------------------------------------------
    # A pattern Kivi merely noticed is not a rule. It becomes active on an
    # explicit instruction, or after this many independent observations.
    "promotion_observations": 3,
    # Below this the candidate is stored as "observed" and shown to the person,
    # never applied.
    "extract_confidence_floor": 0.55,
    # A fact needs to be heard this many times before Kivi offers it, unless
    # the person corrected it in place (which is explicit and counts at once).
    "fact_offer_after_hearings": 2,

    # --- Retrieval ------------------------------------------------------
    "retrieval_top_k": 6,
    # Below this similarity a memory is not considered relevant. Recorded in
    # the trace so a near-miss is visible, not silent.
    "retrieval_floor": 0.12,
    # Recency half-life for episodes, in hours. Episodic memory decays;
    # facts and preferences do not.
    "episode_half_life_hours": 72.0,

    # --- Abstention -----------------------------------------------------
    # Hey Kivi asks instead of guessing when the top two intents are this
    # close, or when the winner is below the floor.
    "intent_floor": 0.30,
    "intent_margin": 0.08,
    # Referents ("him", "that one") with more than one candidate always ask.
    "ambiguous_referent_asks": True,

    # --- Never learned --------------------------------------------------
    # Categories Kivi refuses to store even when explicitly told to. The
    # refusal is logged with a reason so it is auditable.
    "never_learn": (
        "credential",     # passwords, OTPs, API keys
        "financial_id",   # card numbers, account numbers
        "health",         # medical detail about a person
        "third_party_pii" # someone else's address, phone, ID number
    ),
}

__all__ = [
    "ROOT", "DATA_DIR", "DB_PATH", "CORPUS_PATH",
    "LLM_BACKEND", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "POLICY",
]
