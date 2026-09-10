# Kivi — semantic memory

A working end-to-end product, not a prototype with a backend attached. The
interface, the memory system, the retrieval and the evaluation are one thing,
and every visible behaviour comes from real state in SQLite.

**Run it:** see [docs/RUN.md](docs/RUN.md). Primary review method is a completely local
application: `pip install`, `python backend/manage.py migrate`, `python backend/manage.py seed`, `python app.py`.
No API key, no container, no database server.

| | |
| --- | --- |
| Positioning statement | [`docs/POSITION.md`](docs/POSITION.md) |
| Vision document | [`docs/VISION.md`](docs/VISION.md) |
| How to run and review | [`docs/RUN.md`](docs/RUN.md) |
| Evaluation results | [`evaluation/REPORT.md`](evaluation/REPORT.md) · [`results.json`](evaluation/results.json) |
| Schema and migrations | [`database/migrations/`](database/migrations/) |
| Corpus and generator | [`resources/corpus/`](resources/corpus/) |

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
`backend/kivi/config.py → POLICY["dictation_reads"]`, applied in
`backend/kivi/heykivi/run.py → dictate()`. Every dictation trace opens with a
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
backend/kivi/api.py     Flask: /api/dictate, /api/ask, /api/memory, /api/trace
backend/kivi/heykivi/   routing, abstention, tool chaining, the dictation path
backend/kivi/memory/    creation, promotion, conflict, supersession, provenance
backend/kivi/llm.py     adapter: local (default) | anthropic
backend/kivi/local_model.py deterministic intent, extraction, reshaping
backend/kivi/trace.py  per-request decision record
   │
SQLite                  utterance · memory · memory_event · trace · trace_step
```

The repository is organized so the backend is one unit under `backend/`, data
under `resources/`, schema under `database/`, evaluation under `evaluation/`,
and the browser surface under `extension/`.

## Database, schema and migrations

Embedded SQLite at `data/kivi.db`. The schema lives in `database/migrations/` and
runs once in filename order inside a transaction.

## Evaluation

`python evaluation/run_eval.py` runs the corpus through the real ingestion path
and then the fixed Hey Kivi cases. Current results are retained in
`evaluation/results.json` and summarized in `evaluation/REPORT.md`.

## Reproducibility

- `python backend/verify.py` checks the stack in one command.
- `python resources/corpus/generate.py` regenerates the synthetic corpus.
- `python backend/manage.py seed` loads it through the real ingestion path.
- `python evaluation/run_eval.py` re-runs the evaluation harness.

## Use of AI in this work

The implementation in this repository was built with Claude; the product
positioning and vision documents are the author's own work. The consequential
memory boundaries, promotion gate, refusal policy, tools, evaluation design,
and product decisions remain explicitly defended in this repository.
