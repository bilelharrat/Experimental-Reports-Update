"""Append-only JSONL progress log.

A single small primitive used by long-running jobs (deck summary today,
report generation tomorrow) to emit granular progress that the frontend
can consume via SSE. The disk file doubles as a durable record so the
user can replay events if they reload mid-job.

Each line is one JSON object with at minimum `{type, ts}` plus any
job-specific fields the caller wants to attach.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProgressLog:
    """Thread-safe writer for a JSONL progress file."""

    TERMINAL_TYPES = ("done", "error")

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Truncate so a re-run doesn't surface the old log.
        self.path.write_text("", encoding="utf-8")

    def emit(self, type_: str, **fields: Any) -> None:
        entry = {
            "type": type_,
            "ts": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()

    @property
    def is_terminated(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in reversed(f.readlines()[-10:]):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("type") in self.TERMINAL_TYPES:
                        return True
        except Exception:
            return False
        return False
