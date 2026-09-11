#!/usr/bin/env python3
"""Start Kivi. Serves the API and the interface from one process."""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kivi.api import app

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    print(f"Kivi on http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, debug=False)
