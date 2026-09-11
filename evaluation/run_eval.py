#!/usr/bin/env python3
from pathlib import Path
import runpy
ROOT=Path(__file__).resolve().parent.parent
legacy=ROOT/'evaluation'/'_legacy_eval.py'
links=[]
for name,target in [('kivi',ROOT/'backend'/'kivi'),('corpus',ROOT/'resources'/'corpus')]:
    p=ROOT/name
    if not p.exists():
        p.symlink_to(target,target_is_directory=True); links.append(p)
try:
    runpy.run_path(str(legacy),run_name='__main__')
finally:
    for p in links:
        try:p.unlink()
        except OSError:pass
