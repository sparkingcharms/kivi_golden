"""Reading corpus files.

Corpus records carry an absolute `ts`, so the file is reproducible byte for
byte, and a `gen_ts` recording when the corpus was generated.

At load time every record is shifted forward by the whole number of days
between `gen_ts` and today. Without this, a corpus generated in September has
"yesterday" baked in as a fixed calendar date, and the moment anyone clones the
repository a day later, "find the dictation I did around 5 PM yesterday"
matches nothing.

The shift is in whole days rather than raw seconds so the time of day survives:
a record made at 17:12 stays at 17:12, which is what a query saying "around
5 PM" is actually asking about.

Records without `gen_ts` keep whatever `ts` they carry, so an imported corpus
with real timestamps behaves as its author intended.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

REQUIRED_FIELDS = ("raw_asr", "app")


DAY = 86400.0


def day_shift(gen_ts: float, ref: float | None = None) -> float:
    """Seconds to add so the corpus lands on today, aligned to whole days."""
    ref = ref if ref is not None else time.time()
    gen_day = datetime.fromtimestamp(gen_ts).date()
    ref_day = datetime.fromtimestamp(ref).date()
    return (ref_day - gen_day).days * DAY


def rebase(record: dict[str, Any], ref: float | None = None,
           shift: float | None = None) -> dict[str, Any]:
    """Move one record forward to the current week, preserving time of day."""
    gen = record.get("gen_ts")
    if gen is None and shift is None:
        return record
    if shift is None:
        shift = day_shift(float(gen), ref)
    if not shift:
        return record
    out = dict(record)
    out["ts"] = float(record.get("ts", 0.0)) + shift
    return out


def read(path: Path | str, rebase_time: bool = True,
         strip_labels: bool = True) -> Iterator[tuple[int, dict | None, str | None]]:
    """Yield (line_number, record, error). Exactly one of record/error is set."""
    ref = time.time()
    shift: float | None = None
    with Path(path).open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                yield i, None, "not valid JSON"
                continue
            missing = [f for f in REQUIRED_FIELDS if not rec.get(f)]
            if missing:
                yield i, None, f"missing {', '.join(missing)}"
                continue
            if strip_labels:
                rec.pop("expect", None)      # evaluation labels are not product data
            if rebase_time:
                if shift is None and rec.get("gen_ts"):
                    shift = day_shift(float(rec["gen_ts"]), ref)
                rec = rebase(rec, ref, shift)
            rec.setdefault("formatted", rec["raw_asr"])
            yield i, rec, None


def load(path: Path | str, **kwargs) -> list[dict[str, Any]]:
    """All valid records, errors discarded."""
    return [rec for _, rec, err in read(path, **kwargs) if rec is not None]
