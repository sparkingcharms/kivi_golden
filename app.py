#!/usr/bin/env python3
"""Start the local Kivi application."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
from kivi.api import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"Kivi on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
