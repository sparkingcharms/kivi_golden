# Kivi — semantic memory

A working end-to-end product, not a prototype with a backend attached. The
interface, the memory system, the retrieval and the evaluation are one thing,
and every visible behaviour comes from real state in SQLite.

**Run it:** see [RUN.md](RUN.md). Primary review method is a completely local
application: `pip install`, `manage.py migrate`, `manage.py seed`, `run.py`.
No API key, no container, no database server.

| | |
| --- | --- |
| Positioning statement | [`docs/POSITION.md`](docs/POSITION.md) |
| Vision document | [`docs/VISION.md`](docs/VISION.md) |
| How to run and review | [`RUN.md`](RUN.md) |
| Evaluation results | [`evaluation/REPORT.md`](evaluation/REPORT.md) · [`results.json`](evaluation/results.json) |
| Schema and migrations | [`migrations/`](migrations) |
| Corpus and generator | [`corpus/`](corpus) |

---

## Use cases

The build works backwards from four things a person actually does, not from
what a memory system could infer.

**1. Recover something you already said, and reuse it.**
*"Find the dictation I did around 5 PM yesterday in Slack and polish it for the
meeting I'm walking into."* One sentence, two requests. Episodic memory locates
it by time and app; preference memory rewrites it. Kivi proposes; you press
Apply.

**2. Stop re-correcting the same word.**
You fix *Sharvam* to *Sarvam AI* once, in place, mid-dictation. Every later
dictation writes it correctly, in any app. This is the only kind of memory
allowed to touch ordinary dictation, because it is Kivi fixing its own error
rather than editing your intent.

**3. Teach how you write, once.**
*"Remember that I keep emails to three sentences."* It applies when you ask
Kivi for something, and never while you are dictating. Rules name their own
scope: a rule about Slack updates does not fire in Gmail.

**4. Know what it has picked up, and take it back.**
Everything Kivi has inferred but not earned sits visible under *Noticed, not
applied*, with a count of how many more sightings it needs. Confirm or dismiss
in one click. Nothing is stored that you cannot see, trace to its original
sentence, or remove.

Everything else a memory system could do here — remembering facts about the
world from your dictation, building a profile, acting on your behalf — was
deliberately left out. See *The shape of the decision* below.

---

## The shape of the decision

A memory system can learn a great deal. Most of it is not worth having. The
question this build answers is not "what could Kivi infer" but "what should
Kivi be allowed to act on", and the answer is narrower than the capability.

Three kinds of memory exist here, and one boundary separates them.

| kind | what it is | example | who may read it |
| --- | --- | --- | --- |
| `fact` | a word Kivi got wrong and you fixed | `Sharvam → Sarvam AI` | dictation **and** Hey Kivi |
| `preference` | a durable rule about how output is written | *Keep emails to three sentences* | Hey Kivi only |
| `episode` | one dictation, with app and time | *"Quick update: the third seed finished…"* | Hey Kivi only |

**Ordinary dictation reads facts and nothing else.** This is the central
decision. When you are dictating, Kivi is a transcription surface: it may
replace a word it previously misheard, because that is fixing its own error.
It may not shorten your sentence, change your register, or apply a rule you
taught it last week — that would be Kivi editing your intent while you are
mid-thought, and you would stop trusting what appears in the box.

**Hey Kivi reads everything.** An interactive request is you asking for
judgement. That is where accumulated understanding belongs, and where it pays
for itself.

The boundary is enforced in code, not by convention:
`kivi/config.py → POLICY["dictation_reads"]`, applied in
`kivi/heykivi/run.py → dictate()`. Every dictation trace opens with a
`memory_scope` step naming what it was allowed to read.

## What the system refuses to learn

Four categories are never stored, even when you explicitly ask
(`POLICY["never_learn"]`): credentials, financial identifiers, health detail,
and third-party identity numbers. The check runs before parsing, and in the
hosted-model configuration it stays deterministic — a model is not permitted to
decide that a password is safe to keep.

It refuses the *value*, not the subject. "The OTP step was the block in
onboarding" is a sentence about a product metric and is stored normally; "the
OTP is 449281" is refused. Getting this distinction wrong in the first pass is
what the evaluation caught (see *What went wrong* below).

Beyond that, Kivi does not store the content of what you said as a fact about
the world. If you dictate "the meeting moved to 4", Kivi keeps the episode, not
a belief about your calendar. It learns how you write, not what is true.

## The promotion gate

An explicit instruction or an in-place correction becomes active immediately —
you said it, and asking again would be rude.

Behaviour that Kivi merely noticed does not. It is stored as `observed`,
**never applied**, and shown to you with a count: *"you edited Kivi's output —
noticed, not applied · 2 more sightings before it applies"*. It activates after
three independent sightings, or the moment you press *Make it a rule*.

This is how the product keeps you in control without making you its
administrator. There is no settings page to maintain. The only things asking
for your attention are the handful of guesses Kivi has not earned yet, and you
can confirm or dismiss each in one click.

## Conflicts

A new rule does not win by being newer. If it contradicts an active rule with
the same scope, it is held and both are shown to you. Scope is not a conflict:
a rule about Slack and a rule about Gmail cannot contradict each other, and a
preference for bullets with no count does not contradict a rule naming three.

Rules also carry the surface they name. *"Always keep my Slack updates to three
bullets"* compiles to `applies_to: Slack` and does not fire when you are
drafting in Gmail.

## The tools

Five, chosen from the use cases rather than from what was possible.

| tool | serves |
| --- | --- |
| `find_dictation` | *"find the dictation I did around 5 PM yesterday in Slack"* |
| `reshape` | *"…and polish it for the meeting I'm walking into"* |
| `recall` | *"what rules are you following for my emails"* |
| `draft_message` | *"tell Arjun the latency numbers are ready"* |
| `remember` / `forget` | teaching and unteaching, by voice |

No tool sends, posts, commits, or writes into another application. Every result
is a proposal with an Apply button. The transport is you.

## Architecture

```
web/index.html          the interface — desktop simulation, Hey Kivi panel,
                        memory surface, and a "why did Kivi do that" drawer
   │  HTTP
kivi/api.py             Flask: /api/dictate, /api/ask, /api/memory, /api/trace
kivi/heykivi/run.py     routing, abstention, tool chaining, the dictation path
kivi/heykivi/tools.py   the five tools
kivi/memory/store.py    creation, promotion, conflict, supersession, provenance
kivi/memory/retrieve.py scoring, time and app parsing, explanations
kivi/llm.py             adapter: local (default) | anthropic
kivi/local_model.py     deterministic intent, extraction, reshaping
kivi/trace.py           per-request decision record
   │
SQLite                  utterance · memory · memory_event · trace · trace_step
```

**Retrieval scoring** is `similarity × recency × app_match`, with an exact
subject bonus for facts. Episodes decay on a 72-hour half-life; facts and
preferences do not, because a spelling you fixed in March is still your
spelling in September.

One case needed a separate path. *"What did I say in WhatsApp yesterday
evening"* contains no content words at all once the time and app are removed —
the filters **are** the query. Scoring it on word overlap returns nothing, so
when fewer than two content terms survive, episodes passing the filters get a
baseline relevance instead. The trace records `filter_driven: true` when this
happens.

**Nothing is overwritten.** Editing a memory retires the old row and points it
at the new one via `superseded_by`, and every memory keeps the id of the
utterance it came from. *Where from* in the interface shows you the original
sentence, the app, and the time.

## Database, schema and migrations

Embedded SQLite at `data/kivi.db`. Five tables:

| table | holds |
| --- | --- |
| `utterance` | every dictation event: raw ASR, formatted output, app, time, language mix, privacy flag |
| `memory` | facts, preferences and episodes, with status, confidence, observation count, scope, origin, reason and `superseded_by` |
| `memory_event` | every time a memory was observed, promoted, applied, edited, retired or rejected |
| `trace` | one row per request: intent, confidence, outcome, latency, model calls, tokens, cost |
| `trace_step` | the ordered decision steps behind that request |

The schema lives in `migrations/*.sql`, never inline in the code. Each file
runs once, in filename order, inside a transaction, and is recorded in
`schema_migrations`.

- `001_initial.sql` — the five tables and their primary indexes
- `002_retrieval_indexes.sql` — covering indexes for the retrieval hot path

`python manage.py migrate` applies what is pending and is safe to run
repeatedly; `python manage.py status` shows the applied version. Starting the
app migrates automatically, so it is never running against a half-migrated
database.

## Inspecting a decision

Every request writes a trace: intent scores against the abstention floor, the
retrieval candidates **including the ones below the floor**, which rules were in
force, which actually changed something, which were considered and unused, and
what was deliberately ignored.

- in the product: the *Why did Kivi do that?* drawer under the desktop
- over HTTP: `GET /api/trace/<id>`, `GET /api/traces`
- in the evaluation: `evaluation/results.json → end_to_end[].trace_steps`

A near-miss is visible rather than absent, which is the difference between
debugging retrieval and guessing at it.

## Evaluation

`python evaluation/run_eval.py` runs all 500 corpus records through the real
ingestion path, then runs a fixed set of Hey Kivi requests against the
resulting database. Current results, local backend:

| measure | result |
| --- | --- |
| Fact recall | 100% |
| Fact direction correct | 100% |
| Preference activation | 100% |
| Observed, not applied | 100% |
| Refusal | 100% |
| Reminder capture | 100% |
| False facts / false preferences | 0 / 0 |
| Retrieval | 100% |
| End-to-end | 100% (13 cases) |

Ingest p50 0.5 ms, p95 0.7 ms. Database 4.9 MB after 500 records, ~9.8 KB per
record. Local backend: 0 model calls, $0.

Read these as a regression harness, not as a claim of general accuracy. The
corpus is synthetic and I wrote both the corpus and the extractor, so high
scores mean the system does what I specified on inputs I anticipated. The
useful signal is in the two zeros — no invented facts and no invented rules
across 500 records — and in the cases where a first version failed.

## What went wrong, and what it changed

The evaluation existed to catch things, and it did.

1. **Episodes were stamped with ingest time, not speech time.** Every time
   query returned nothing. Fixed by threading the utterance timestamp through
   ingestion.
2. **Corrections were learned backwards.** One pattern read *"Arjun, not
   Arjuna"* as *Arjun → Arjuna*, teaching Kivi the error. The direction is now
   explicit in the group names, and `fact_direction_correct` measures it
   separately from recall.
3. **The refusal was too eager.** "The OTP step was the block in onboarding"
   was refused as a credential. A credential is a word *plus a value*; the
   patterns now require one.
4. **A weak preference reshaped everything.** *"Prefer bullets over paragraphs
   for updates"* turned a one-line draft into a single bullet. Bullets are now
   forced only when a count is named or the request asks for them.
5. **Rules ignored the surface they named.** A Slack rule fired in Gmail.
   Rules now compile an `applies_to` scope.

## Known limitations

- The local backend is rule-driven. It handles the constructions in the corpus
  and abstains or misses outside them. `KIVI_LLM=anthropic` swaps in a hosted
  model at the same three call sites without touching the memory system.
- Sentence splitting is naive, so *"One. Ship the prototype."* becomes two
  bullets.
- Near-duplicate rules can both stay active (*"Keep emails to three sentences
  unless I ask for more"* alongside *"I keep emails to three sentences"*).
  Conflict detection catches contradiction, not redundancy. Merging
  near-duplicates is the next thing I would build.
- Rule scope is inferred from app names in the rule text. A rule about "my
  updates" has no structural scope and applies everywhere.
- Single-user. There is no auth, no tenancy, no encryption at rest.
- The corpus is template-and-slot synthesis, deliberately not model-generated:
  a corpus written by the model under test measures agreement with itself.

## Reproducibility

- `python verify.py` checks the entire stack in one command — runtime,
  dependencies, migrations, corpus, seeding, the four headline behaviours, the
  dictation boundary, traces, the API, and the interface. It exits non-zero if
  anything fails.
- Corpus timestamps are rebased on load. Each record carries the moment the
  corpus was generated, and the loader shifts every record forward by whole
  days, so "the dictation I did around 5 PM yesterday" still means yesterday at
  5 PM however long after generation the repository is cloned. Whole days
  rather than raw seconds, so the time of day survives the shift.
- `python corpus/generate.py` regenerates the 500-record corpus byte for byte
  from a fixed seed (`SEED = 20260905`). It is template-and-slot synthesis, not
  model output.
- `python manage.py seed` loads it through the real ingestion path — the same
  code the interface calls — so the memory state you review was learned, not
  inserted.
- `python evaluation/run_eval.py` drops the database, re-migrates, re-ingests
  everything and re-runs all 13 end-to-end cases. Two runs on the same machine
  produce the same scores; only latency figures move.

## Use of AI in this work

Stated plainly, because the brief asks and because it affects how the rest of
this document should be read.

**Where AI was used.** The implementation in this repository was built with
Claude: the Python modules under `kivi/`, the interface in `web/`, the corpus
generator, the evaluation harness, the migrations, and this README. I directed
the work, made the product decisions, and reviewed and corrected the output
throughout.

**What that means for the decisions.** The consequential choices here are mine
and I can defend each without the code in front of me:

- which three kinds of memory exist, and why episodic and preference memory are
  kept out of ordinary dictation;
- that inferred rules are shown but never applied until three sightings or a
  confirmation;
- that four categories are refused before parsing, and that the refusal stays
  deterministic even when a hosted model is doing the extraction;
- that there are five tools and none of them send anything;
- that a newer rule does not beat an older one by being newer;
- what the evaluation measures, and what its numbers do not prove.

**Where AI was not used.** The positioning statement and vision document
(`docs/`) are my own work, written without generative AI, as Part One requires.

**Bugs AI introduced that I caught.** Listed in full under *What went wrong*
above. Two were serious: episodes were stamped with ingest time rather than
speech time, which silently broke every time-based query; and one extraction
pattern read corrections backwards, teaching the misspelling instead of the
correction. Both were found by the evaluation, which is the reason the
evaluation exists and the reason `fact_direction_correct` is scored separately
from `fact_recall`.

**The honest limit.** The local model backend is rule-driven and I wrote both
the rules and the corpus that tests them, so the scores show the system does
what I specified on inputs I anticipated. They are a regression harness, not a
claim of general accuracy. The two zeros — no invented facts, no invented rules
across 500 records — are the numbers I would defend.
