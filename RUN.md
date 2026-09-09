# RUN.md

## Primary review method

**A completely local application.** One Python process serves both the
interface and the backend; the database is embedded SQLite created on disk by
the migration command. There is no container, no hosted service, no account,
and **no LLM key is required** — the default model backend is deterministic and
runs offline.

Clone to working interface: about a minute.

**macOS / Linux**

```
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py seed
python3 verify.py
python3 run.py                     # then open http://127.0.0.1:8000
```

**Windows (PowerShell or Command Prompt)** — identical, with `python` instead
of `python3`:

```
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python verify.py
python run.py
```

Everywhere below, Windows users read `python` for `python3`. Nothing else
differs — there are no shell scripts, no Makefile, and no path separators in
any command.

### Confirming it all works

```
python3 verify.py
```

One command, no server needed. It checks the Python version, the dependencies,
that every required file exists, that the migrations build the schema and are
idempotent, that the corpus loads and rebases, that seeding produces memory,
that the four headline behaviours work (chained lookup, learned spellings,
refusal, asking instead of guessing), that the dictation boundary is enforced,
that traces are written, that the API and interface both serve, and that port
8000 is free. It prints a line per check and exits non-zero if anything failed.

It runs against a scratch database and never touches your working data.

---

## 1. Required runtimes and versions

| requirement | version | notes |
| --- | --- | --- |
| Python | **3.10 or newer** | developed and verified on 3.12.3 |
| SQLite | bundled with Python | no server to install |

Nothing else. No Node, no Docker, no database server.

```
python3 --version
```

## 2. Required environment variables

**None.** The application runs with no environment configuration.

Every variable below is optional, with its default.

| variable | default | effect |
| --- | --- | --- |
| `KIVI_LLM` | `local` | model backend: `local` or `anthropic` |
| `ANTHROPIC_API_KEY` | *(unset)* | **the LLM key variable.** Read only when `KIVI_LLM=anthropic`. If that is set without a key, the app falls back to `local` rather than failing. |
| `KIVI_MODEL` | `claude-sonnet-4-6` | model name for the `anthropic` backend |
| `KIVI_DATA_DIR` | `./data` | where the database is written |
| `KIVI_DB` | `./data/kivi.db` | full database path |
| `KIVI_CORPUS` | `./corpus/corpus.jsonl` | corpus used by `seed` |

## 3. Install dependencies

```
pip install -r requirements.txt
```

Flask and requests. `requests` is used only by the optional hosted-model
backend; the default path never imports it.

## 4. Create, migrate and seed the database

```
python3 manage.py migrate
python3 manage.py seed
```

`migrate` creates `data/kivi.db` and applies every file in `migrations/` in
order, recording each in `schema_migrations`. Running it twice applies nothing
the second time.

`seed` loads the 500-record corpus through the real ingestion path — the same
code the interface uses, not a bulk insert — so the memory state under review
was genuinely learned. A few seconds. It refuses to double-load.

Both commands are optional: starting the app applies pending migrations
automatically, and the interface seeds itself on first load if the database is
empty. They are listed separately so the sequence is explicit and scriptable.

## 5. Start every required process

```
python3 run.py
```

**One process.** It serves the API and the interface together. Add
`--port 8080` if 8000 is taken.

## 6. What to open

**http://127.0.0.1:8000**

The status line at the top right shows the dictation count once seeding has
finished.

## 7. Primary interactions to try

Each is a one-click chip beneath the input box.

1. **The chained request.** *Hey Kivi:* "find the dictation I did around 5 PM
   yesterday in Slack and polish it for the meeting I'm walking into." Kivi
   finds the right Slack entry, rejects a WhatsApp entry from the same hour and
   a Slack entry from a different day, then rewrites it. Nothing changes in the
   app until you press Apply.
2. **Teaching a word.** On the Slack tab, press *Dictate* on "no — Sarvam AI,
   not Sharvam." Then dictate "Numbers for the Sharvam pilot are in the sheet."
   The spelling is corrected in place and appears under *Words it has learned*.
3. **The boundary.** Dictate anything and read the panel: it names the memory
   it was allowed to use. Ordinary dictation may fix a spelling and may not
   reshape your wording.
4. **The refusal.** *Hey Kivi:* "remember that my portal password is
   kivi@2026." Declined, with the category named.
5. **Asking instead of guessing.** *Hey Kivi:* "send this to him." Two people
   could be *him*, so Kivi asks.
6. **The promotion gate.** *Noticed, not applied* on the right lists rules Kivi
   inferred but has not earned, with how many more sightings each needs.
   *Make it a rule* promotes one; *Not a rule* drops it.
7. **Provenance.** *Where from* on any rule shows the original sentence, its
   app and its time.
8. **Why.** Open *Why did Kivi do that?* under the desktop after any action.

## 8. Run the candidate evaluation

```
python3 evaluation/run_eval.py
```

Rebuilds the database from scratch, runs all 500 corpus records through the
real ingestion path, then runs 13 end-to-end Hey Kivi cases against the
resulting state. Prints a scoreboard and writes two files. A few seconds.

With the hosted backend, which also reports token counts and dollar cost:

```
KIVI_LLM=anthropic ANTHROPIC_API_KEY=sk-... python3 evaluation/run_eval.py
```

> The evaluation resets the database. Restore it with
> `python3 manage.py reset --seed` before using the interface again.

## 9. Importing another corpus

Records are JSON Lines, one object per line. Only `raw_asr` and `app` are
required:

```json
{"raw_asr": "no — Sarvam AI, not Sharvam", "app": "Slack"}
```

Optional: `formatted` (defaults to `raw_asr`), `ts` (unix seconds, defaults to
now — set it if you want time queries to work), `languages` (defaults to
`["en"]`), `private` (bool), `meta` (object; `meta.user_edit` describes an edit
the person made afterwards and is what drives the promotion gate). An `expect`
field, if present, is stripped: evaluation labels are not product data.

```
python3 manage.py import-corpus path/to/your.jsonl
python3 manage.py import-corpus path/to/your.jsonl --limit 100
```

Malformed lines and records missing required fields are reported and skipped;
the rest still load. To review a different corpus from a clean state:

```
python3 manage.py reset
python3 manage.py import-corpus path/to/your.jsonl
```

To regenerate the bundled corpus (deterministic, byte-identical each run):

```
python3 corpus/generate.py
```

## 10. Where to inspect evaluation results and memory state

**Evaluation results**

| where | what |
| --- | --- |
| `evaluation/REPORT.md` | scores, cost, latency, growth, per-case table |
| `evaluation/results.json` | every case with its full trace: input, memory created or rejected, provenance, resulting behaviour, reason |

**Memory state**

| where | what |
| --- | --- |
| right-hand column of the interface | words learned, rules in force, noticed-not-applied, recent dictations |
| `GET /api/memory` | the same data as JSON |
| `GET /api/memory/<id>/history` | provenance and event log for one memory |
| `python3 manage.py status` | schema version, counts by kind and status |
| `python3 manage.py inspect <memory_id>` | one memory, its source sentence, its history |
| `data/kivi.db` | open with any SQLite client |

**Why a request behaved as it did**

| where | what |
| --- | --- |
| *Why did Kivi do that?* drawer | the last request's decision steps |
| `GET /api/trace/<id>` · `GET /api/traces` | any trace |
| `python3 manage.py inspect --trace <trace_id>` | the same, on the command line |

A trace records intent scores against the abstention floor, retrieval
candidates **including those below the floor**, which rules were in force,
which changed something, which were considered and unused, and what was
deliberately ignored.

## 11. Resetting the system

```
python3 manage.py reset          # drop the database, re-apply migrations
python3 manage.py reset --seed   # ...and re-load the bundled corpus
```

Or delete the directory — the next start recreates and re-seeds it:

```
rm -rf data/          # macOS / Linux
rmdir /s /q data      # Windows Command Prompt
Remove-Item -Recurse -Force data   # Windows PowerShell
```

---

## Troubleshooting

- **Port in use:** `python3 run.py --port 8080`. `verify.py` warns about this
  before you start.
- **`python3` not recognised (Windows):** use `python`. If that also fails,
  Python is not on your PATH — reinstall it with "Add Python to PATH" ticked.
- **`pip` not recognised:** use `python -m pip install -r requirements.txt`.
- **Right column empty:** first-load seeding is still running; wait for the
  status line.
- **`no corpus at ...`:** run `python3 corpus/generate.py` first.
- **Fonts look wrong offline:** Barlow loads from Google Fonts and falls back to
  the system sans. Nothing else touches the network on the default backend.
