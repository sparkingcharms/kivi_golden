#!/usr/bin/env python3
"""Reproducible evaluation of the whole pipeline."""
from __future__ import annotations
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"backend"))
from kivi import corpus_io
from kivi.config import DB_PATH,POLICY
from kivi.db import connect,db_size_bytes,jload,reset
from kivi.heykivi.run import ask,dictate
from kivi.llm import get_backend
from kivi.memory import retrieve
CORPUS=ROOT/"resources"/"corpus"/"corpus.jsonl"
OUT_JSON=ROOT/"evaluation"/"results.json"
OUT_MD=ROOT/"evaluation"/"REPORT.md"
