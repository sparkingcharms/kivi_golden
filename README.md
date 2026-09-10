# Kivi — semantic memory

A working end-to-end product, not a prototype with a backend attached. The interface, memory, retrieval and evaluation are one system, with visible behaviour backed by real SQLite state.

**Run it:** see [docs/RUN.md](docs/RUN.md). Primary review path: `pip install`, `python backend/manage.py migrate`, `python backend/manage.py seed`, `python app.py`.

| | |
| --- | --- |
| Positioning statement | [`docs/POSITION.md`](docs/POSITION.md) |
| Vision document | [`docs/VISION.md`](docs/VISION.md) |
| How to run and review | [`docs/RUN.md`](docs/RUN.md) |
| Evaluation results | [`evaluation/REPORT.md`](evaluation/REPORT.md) · [`evaluation/results.json`](evaluation/results.json) |
| Schema and migrations | [`database/migrations/`](database/migrations/) |
| Corpus and generator | [`resources/corpus/`](resources/corpus/) |

---

## Use cases

**1. Recover something you already said, and reuse it.**
*"Find the dictation I did around 5 PM yesterday in Slack and polish it for the meeting I'm walking into."* One sentence, two requests. Episodic memory locates it by time and app; preference memory rewrites it. Kivi proposes; you press Apply.

**2. Stop re-correcting the same word.**
You fix *Sharvam* to *Sarvam AI* once, in place, mid-dictation. Later dictation writes it correctly. This is the only kind of memory allowed to touch ordinary dictation, because it fixes Kivi's own error rather than editing your intent.

**3. Teach how you write, once.**
*"Remember that I keep emails to three sentences."* It applies when you ask Kivi for something, and never while you are dictating. Rules name their own scope.

**4. Know what it has picked up, and take it back.**
Everything Kivi has inferred but not earned sits visible under *Noticed, not applied*, with a count of how many more sightings it needs. Confirm or dismiss in one click.

Everything else a memory system could do here was deliberately left out. The build answers not "what could Kivi infer" but "what should Kivi be allowed to act on".

## Memory model

Kivi separates four kinds of remembered context:

| kind | what it is | who may read it |
| --- | --- | --- |
| `fact` | useful personal vocabulary or stable information | dictation and Hey Kivi |
| `preference` | a durable rule about how output is written | Hey Kivi only |
| `episode` | one dictation, with app and time | Hey Kivi only |
| `shortcut` | a user-defined phrase mapped to a remembered transformation | Hey Kivi only |

**Ordinary dictation reads facts and nothing else.** The boundary is enforced in code and recorded in each dictation trace.

**Hey Kivi reads everything relevant to the request.** That is where accumulated understanding belongs.

## Shortcuts

Shortcuts use a preview-first teaching flow:

1. Kivi interprets the phrase.
2. Kivi reads back what it thinks the shortcut means.
3. The user confirms before it is saved.
4. Future matches check scope and collisions before applying.
5. Applying a shortcut only produces a draft. Nothing is sent or posted automatically.

Examples include `professorize this` and `standup-ify`. Similar triggers can be surfaced as ambiguous instead of guessed, and app scope is enforced.

## What the system refuses to learn

Four categories are never stored: credentials, financial identifiers, health detail, and third-party identity numbers. The check runs before parsing, and a model is not allowed to decide that a sensitive value is safe to keep.

Kivi also does not turn ordinary dictation into facts about the world. If you dictate "the meeting moved to 4", Kivi keeps the episode, not a belief about your calendar.

## The promotion gate

An explicit instruction or in-place correction becomes active immediately.

Behaviour Kivi merely noticed does not. It is stored as `observed`, never applied, and shown with a count. It activates after three independent sightings, or when you press *Make it a rule*.

## Conflicts

A new rule does not automatically win by being newer. If it contradicts an active rule with the same scope, it is held and both are shown. Scope is enforced, so a Slack rule does not fire in Gmail.

## The tools

| tool | serves |
| --- | --- |
| `find_dictation` | recover a past dictation |
| `reshape` | rewrite selected text |
| `recall` | inspect remembered rules |
| `draft_message` | prepare a message |
| `remember` / `forget` | teaching and unteaching |

No tool sends, posts, commits, or writes into another application. Every result is a proposal with an Apply step.

## Architecture

```text
web/index.html          interface and inspection surface
   │  HTTP
backend/kivi/api.py     Flask API
backend/kivi/heykivi/   routing, abstention, tools, dictation path
backend/kivi/memory/    creation, promotion, conflicts, provenance, shortcuts
backend/kivi/llm.py     model adapter
backend/kivi/local_model.py deterministic local behaviour
backend/kivi/trace.py   per-request decision record
   │
SQLite                  utterance · memory · memory_event · trace · trace_step
```

The repository is organized with the backend under `backend/`, seed data under `resources/`, schema under `database/`, evaluation under `evaluation/`, browser integration under `extension/`, and product/run documents under `docs/`.

## Evaluation

`python evaluation/run_eval.py` runs the corpus through the real ingestion path and the fixed Hey Kivi cases. Results are retained in `evaluation/results.json` and summarized in `evaluation/REPORT.md`.

`python backend/verify.py` checks the stack in one command.

## Chrome extension

The extension connects selected text in browser pages to the local Kivi backend. It is selection-based and does not send or post content itself.

Load `extension/` through Chrome's **Load unpacked** flow. The extension expects Kivi at `http://127.0.0.1:8000`.

## Design documents

- `docs/POSITION.md` contains the Kivi position statement.
- `docs/VISION.md` contains the product vision.
- `docs/PRODUCT_CONTEXT.md` explains the relationship between Kivi and this Golden Goose implementation.
- `docs/assets/` contains the submitted visual/product assets.

## Use of AI in this work

The implementation was built with Claude; the product positioning and vision documents are the author's own work. The consequential memory boundaries, promotion gate, refusal policy, tools, evaluation design, and product decisions are explicitly defended in this repository.
