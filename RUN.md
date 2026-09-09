# Run Kivi

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

The default backend is deterministic and local. No API key is required.

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Migrate and seed

```bash
python manage.py migrate
python manage.py seed
```

The corpus contains 500 synthetic, reproducible records. Seeding goes through the same ingestion path used by the product.

## 3. Verify

```bash
python verify.py
```

This uses a scratch database and checks migrations, corpus loading, memory creation, the chained Slack request, learned spellings, sensitive-content refusal, ambiguity handling, the dictation boundary, traces, the HTTP API and the interface.

## 4. Run

```bash
python run.py
```

Open `http://127.0.0.1:8000`.

To use another port:

```bash
python run.py --port 8080
```

## What to try

### A. Recover and reshape a past dictation

Ask:

> find the dictation I did around 5 PM yesterday in Slack and polish it for the meeting I'm walking into

Kivi retrieves an episode using the app/time filters and then applies the relevant preference. The result is a proposal; the product does not send it.

### B. Correct a word once

Use the dictation surface with a sentence containing `Sharvam`. The seeded memory contains the correction `Sharvam → Sarvam AI`, so ordinary dictation fixes the recognition error in place.

### C. Teach a preference

Ask:

> remember that I keep emails to three sentences

Then ask Kivi to draft an email. The preference is available to Hey Kivi but is deliberately not applied to ordinary dictation.

### D. Test the privacy boundary

Ask:

> remember that my portal password is kivi@2026

Kivi declines to store it. The policy rejects sensitive values before model-based extraction.

### E. Test abstention

Ask:

> send this to him

Without enough recipient/context, Kivi asks instead of guessing.

### F. Inspect provenance

The memory surface shows what Kivi knows, whether it is active or merely noticed, and where it came from. The `Why did Kivi do that?` drawer shows the trace for a request.

## Evaluation

Run:

```bash
python evaluation/run_eval.py
```

This executes the deterministic regression corpus and rewrites:

- `evaluation/results.json`
- `evaluation/REPORT.md`

The evaluator covers fact recall, direction correctness, preference activation, observed-but-not-applied behaviour, refusal, reminder capture, false facts/preferences, retrieval, and end-to-end Hey Kivi cases.

## Corpus

`corpus/corpus.jsonl` is the reproducible seed corpus. To regenerate it:

```bash
python corpus/generate.py
```

The generator uses a fixed seed and rebases timestamps so the corpus remains recent enough for time-based product examples while preserving relative timing.

## Database commands

```bash
python manage.py status
python manage.py inspect <memory_id>
python manage.py inspect --trace <trace_id>
```

Reset the local database:

```bash
python manage.py reset --seed
```

The database is stored at `data/kivi.db` and is ignored by git.

## Optional hosted model

The code includes an Anthropic adapter, but the local deterministic backend is the default and is sufficient for the complete evaluation. To use a hosted model, set the required environment variables documented in `kivi/config.py` and `README.md`.

## Reproducibility note

A clean checkout should be sufficient to reproduce the evaluation: install the two declared dependencies, run the migrations, seed the corpus, and run the evaluator. No external database or API service is part of the default path.
