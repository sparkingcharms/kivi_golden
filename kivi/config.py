"""Configuration and policy constants."""
from __future__ import annotations
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DATA_DIR=Path(os.environ.get("KIVI_DATA_DIR",ROOT/"data"))
DB_PATH=Path(os.environ.get("KIVI_DB",DATA_DIR/"kivi.db"))
CORPUS_PATH=Path(os.environ.get("KIVI_CORPUS",ROOT/"corpus"/"corpus.jsonl"))
DATA_DIR.mkdir(parents=True,exist_ok=True)
LLM_BACKEND=os.environ.get("KIVI_LLM","local")
ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY","")
ANTHROPIC_MODEL=os.environ.get("KIVI_MODEL","claude-sonnet-4-6")
POLICY={
 "dictation_reads":("fact",),"heykivi_reads":("fact","preference","episode"),
 "promotion_observations":3,"extract_confidence_floor":0.55,"fact_offer_after_hearings":2,
 "retrieval_top_k":6,"retrieval_floor":0.12,"episode_half_life_hours":72.0,
 "intent_floor":0.30,"intent_margin":0.08,"ambiguous_referent_asks":True,
 "never_learn":("credential","financial_id","health","third_party_pii")}
__all__=["ROOT","DATA_DIR","DB_PATH","CORPUS_PATH","LLM_BACKEND","ANTHROPIC_API_KEY","ANTHROPIC_MODEL","POLICY"]
