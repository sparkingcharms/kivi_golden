# Run Kivi

## 1. Install

Python 3.10+ is required.

```bash
pip install -r requirements.txt
```

## 2. Migrate and seed

```bash
python backend/manage.py migrate
python backend/manage.py seed
```

The app uses a local SQLite database. No database server or API key is required for the default deterministic local backend.

## 3. Start

```bash
python app.py
```

Then open `http://127.0.0.1:8000`.

Use `python app.py --port 8080` if port 8000 is already in use.

## 4. Verify

```bash
python backend/verify.py
```

This checks the schema, corpus, memory ingestion, retrieval, refusal behaviour, dictation boundary, shortcuts, API, interface and Chrome extension manifest.

## 5. Evaluation

```bash
python evaluation/run_eval.py
```

This runs the full corpus and end-to-end evaluation. It resets the evaluation database and writes the results to `evaluation/results.json` and `evaluation/REPORT.md`.

## 6. Chrome extension

1. Start Kivi on `127.0.0.1:8000`.
2. Open Chrome extensions and enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the `extension/` folder.
5. Select text on a supported webpage and invoke Kivi from the extension.

The extension is selection-based. It sends selected text to the local Kivi backend for a proposed transformation. It does not send, post or submit anything to the host application.

## Useful commands

```bash
python backend/manage.py status
python backend/manage.py reset --seed
python backend/manage.py inspect <memory_id>
python backend/manage.py inspect --trace <trace_id>
```

The database is stored under `data/` by default. Set `KIVI_DATA_DIR` or `KIVI_DB` to change its location.
