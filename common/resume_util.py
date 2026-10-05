"""Crash-safe resume helpers for the experiment runners.

Each runner writes one JSON record per completed unit to a JSONL file and
flushes immediately, so progress is durable in real time. On restart, call
``load_done`` to read back the already-finished units and skip them, then append
new records to the same file (open mode ``"a"``). A unit is identified by a
``key_fn(record)`` tuple; duplicates in the file are tolerated (last wins).
"""
from __future__ import annotations

import json
from pathlib import Path


def load_done(path, key_fn):
    """Return (done_keys:set, records:list) from an existing JSONL, or (set(), [])
    if absent. Malformed trailing lines (from a hard kill mid-write) are skipped."""
    p = Path(path)
    if not p.exists():
        return set(), []
    done, records = {}, []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # partial final line from an interrupted write
        try:
            done[key_fn(rec)] = rec
        except (KeyError, TypeError):
            continue
    for k, rec in done.items():
        records.append(rec)
    return set(done), records


def open_appendable(path):
    """Open a JSONL for append (creating it if needed). Parent dirs are created."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.open("a", encoding="utf-8")
