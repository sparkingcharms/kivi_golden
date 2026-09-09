#!/usr/bin/env python3
"""Database and corpus management.

    python manage.py migrate                    create or migrate the database
    python manage.py seed                       load the bundled corpus
    python manage.py import-corpus FILE.jsonl   load a different corpus
    python manage.py reset [--seed]             drop everything and start over
    python manage.py status                     schema version and memory counts
    python manage.py inspect MEMORY_ID          provenance of one memory
    python manage.py inspect --trace TRACE_ID   the decisions behind one request

Every command is idempotent where it can be: `migrate` twice applies nothing
the second time, and `seed` refuses to double-load an already-seeded database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kivi import corpus_io  # noqa: E402
from kivi import db as dbmod  # noqa: E402
from kivi import trace as trace_mod  # noqa: E402
from kivi.config import CORPUS_PATH, DB_PATH  # noqa: E402
from kivi.heykivi.run import dictate  # noqa: E402
from kivi.memory import store  # noqa: E402


def cmd_migrate(args) -> int:
    conn = dbmod.connect(auto_migrate=False)
    todo = dbmod.pending(conn)
    if not todo:
        print(f"database at {DB_PATH} is up to date "
              f"({len(dbmod.applied(conn))} migration(s) applied)")
        return 0
    print(f"applying {len(todo)} migration(s) to {DB_PATH}")
    dbmod.migrate(conn, verbose=True)
    conn.close()
    return 0


def _load(conn, path: Path, limit: int | None = None) -> int:
    n = bad = 0
    for lineno, rec, err in corpus_io.read(path):
        if err:
            bad += 1
            print(f"  line {lineno}: {err}, skipped", file=sys.stderr)
            continue
        dictate(conn, rec)
        n += 1
        if limit and n >= limit:
            break
        if n % 100 == 0:
            print(f"  {n}…")
    if bad:
        print(f"  {bad} record(s) skipped")
    return n


def cmd_seed(args) -> int:
    path = Path(args.file) if args.file else CORPUS_PATH
    if not path.exists():
        print(f"no corpus at {path}. Run: python corpus/generate.py", file=sys.stderr)
        return 1
    conn = dbmod.connect()
    existing = conn.execute("SELECT COUNT(*) c FROM utterance").fetchone()["c"]
    if existing and not args.force:
        print(f"already seeded ({existing} utterances). "
              f"Use --force to add anyway, or `reset --seed` to start clean.")
        return 0
    print(f"loading {path}")
    n = _load(conn, path, args.limit)
    counts = _counts(conn)
    conn.close()
    print(f"loaded {n} utterances")
    print(f"  facts {counts['fact']} · rules {counts['preference']} · episodes {counts['episode']}")
    return 0


def cmd_import(args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    conn = dbmod.connect()
    print(f"importing {path}")
    n = _load(conn, path, args.limit)
    counts = _counts(conn)
    conn.close()
    print(f"imported {n} utterances")
    print(f"  facts {counts['fact']} · rules {counts['preference']} · episodes {counts['episode']}")
    return 0


def cmd_reset(args) -> int:
    dbmod.reset(DB_PATH)
    print(f"removed {DB_PATH}")
    conn = dbmod.connect(auto_migrate=False)
    dbmod.migrate(conn, verbose=True)
    conn.close()
    if args.seed:
        return cmd_seed(argparse.Namespace(file=None, force=True, limit=None))
    return 0


def _counts(conn) -> dict[str, int]:
    out = {}
    for kind in ("fact", "preference", "episode"):
        out[kind] = conn.execute(
            "SELECT COUNT(*) c FROM memory WHERE kind=? AND status IN ('active','observed')",
            (kind,),
        ).fetchone()["c"]
    return out


def cmd_status(args) -> int:
    conn = dbmod.connect(auto_migrate=False)
    done = sorted(dbmod.applied(conn))
    todo = dbmod.pending(conn)
    print(f"database      {DB_PATH}")
    print(f"size          {dbmod.db_size_bytes(DB_PATH):,} bytes")
    print(f"migrations    {len(done)} applied" + (f", {len(todo)} pending: {todo}" if todo else ""))
    for v in done:
        print(f"              {v}")
    if todo:
        conn.close()
        return 0
    print(f"utterances    {conn.execute('SELECT COUNT(*) c FROM utterance').fetchone()['c']}")
    for kind in ("fact", "preference", "episode"):
        for status in ("active", "observed"):
            n = conn.execute(
                "SELECT COUNT(*) c FROM memory WHERE kind=? AND status=?", (kind, status)
            ).fetchone()["c"]
            if n:
                print(f"  {kind:11s} {status:9s} {n}")
    print(f"traces        {conn.execute('SELECT COUNT(*) c FROM trace').fetchone()['c']}")
    conn.close()
    return 0


def cmd_inspect(args) -> int:
    conn = dbmod.connect()
    if args.trace:
        t = trace_mod.load(conn, args.trace)
        if not t:
            print("no such trace", file=sys.stderr)
            return 1
        print(f"{t['id']}  {t['surface']}  {t['outcome']}  {t['latency_ms']:.1f}ms")
        print(f"request: {t['request']}")
        print(f"intent : {t['intent']} ({t['intent_conf']})")
        for s in t["steps"]:
            print(f"  {s['seq']}. {s['stage']}")
            print(f"     {json.dumps(s['detail'], ensure_ascii=False)[:400]}")
        conn.close()
        return 0

    row = conn.execute("SELECT * FROM memory WHERE id=?", (args.memory_id,)).fetchone()
    if not row:
        print("no such memory", file=sys.stderr)
        return 1
    print(f"{row['id']}  {row['kind']}  {row['status']}")
    print(f"body        {row['body']}")
    print(f"origin      {row['origin']} — {row['reason']}")
    print(f"seen        {row['observations']}x · used {row['use_count']}x")
    print(f"payload     {row['payload']}")
    if row["superseded_by"]:
        print(f"replaced by {row['superseded_by']}")
    if row["source_utt"]:
        u = conn.execute("SELECT * FROM utterance WHERE id=?", (row["source_utt"],)).fetchone()
        if u:
            print(f"came from   {u['id']} in {u['app']}")
            print(f"            \"{u['raw_asr']}\"")
    print("history:")
    for e in store.history(conn, args.memory_id):
        print(f"  {e['event']:10s} {e['detail']}")
    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Kivi database and corpus management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="create or migrate the database").set_defaults(fn=cmd_migrate)

    p = sub.add_parser("seed", help="load the bundled corpus")
    p.add_argument("--file", help="a different .jsonl corpus")
    p.add_argument("--limit", type=int, help="stop after N records")
    p.add_argument("--force", action="store_true", help="load even if already seeded")
    p.set_defaults(fn=cmd_seed)

    p = sub.add_parser("import-corpus", help="load an additional corpus")
    p.add_argument("file")
    p.add_argument("--limit", type=int)
    p.set_defaults(fn=cmd_import)

    p = sub.add_parser("reset", help="drop the database and re-migrate")
    p.add_argument("--seed", action="store_true", help="re-seed afterwards")
    p.set_defaults(fn=cmd_reset)

    sub.add_parser("status", help="schema version and memory counts").set_defaults(fn=cmd_status)

    p = sub.add_parser("inspect", help="provenance of a memory, or one request trace")
    p.add_argument("memory_id", nargs="?")
    p.add_argument("--trace", help="a trace id instead")
    p.set_defaults(fn=cmd_inspect)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
