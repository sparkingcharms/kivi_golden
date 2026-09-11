# Kivi Golden Goose · Start Here

This repository is the working Golden Goose implementation of **Remember** inside the Kivi product.

## Read these first

1. [`docs/PRODUCT_CONTEXT.md`](docs/PRODUCT_CONTEXT.md) · how this implementation fits the broader Kivi product
2. [`docs/POSITION.md`](docs/POSITION.md) · Kivi's product position
3. [`docs/VISION.md`](docs/VISION.md) · product vision
4. [`docs/RUN.md`](docs/RUN.md) · setup, verification and evaluation
5. [`README.md`](README.md) · architecture, memory model and product decisions
6. [`evaluation/REPORT.md`](evaluation/REPORT.md) · evaluation summary

The submitted visual references are in [`docs/assets/`](docs/assets/).

## What this implementation proves

Golden Goose goes deep on **Remember** rather than trying to rebuild every Kivi capability. It implements persistent memory with provenance, refusal boundaries, promotion gates, conflict handling, episodic retrieval and user-defined shortcuts.

The core interaction remains the Kivi model: voice gives the intent, the current screen provides context, Kivi proposes a result, and the user remains the final transport. No tool sends, posts or performs external actions automatically.

## Quick start

```bash
pip install -r requirements.txt
python backend/manage.py migrate
python backend/manage.py seed
python app.py
```

Open `http://127.0.0.1:8000`.

For a complete check:

```bash
python backend/verify.py
```
